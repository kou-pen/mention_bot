import os
from typing import Literal, TypeAlias, cast

import discord


MentionMode: TypeAlias = Literal["and", "or"]

MAX_ROLES = 10
MAX_MESSAGE_LENGTH = 2000
MAX_MESSAGE_INPUT_LENGTH = 1500
MAX_SELECTION_MESSAGE_LENGTH = 1900


intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


async def get_target_members(
    guild: discord.Guild | None,
    selected_roles: list[discord.Role],
    mode: MentionMode,
) -> list[discord.Member]:
    if guild is None or not selected_roles:
        return []

    if not guild.chunked:
        try:
            await guild.chunk(cache=True)
        except discord.HTTPException:
            pass

    return sorted(
        (
            member
            for member in guild.members
            if not member.bot and member_matches_roles(member, selected_roles, mode)
        ),
        key=lambda member: member.display_name.lower(),
    )


def member_matches_roles(
    member: discord.Member,
    selected_roles: list[discord.Role],
    mode: MentionMode,
) -> bool:
    selected_role_ids = {role.id for role in selected_roles}
    member_role_ids = {role.id for role in member.roles}

    if mode == "and":
        return selected_role_ids.issubset(member_role_ids)

    return bool(selected_role_ids.intersection(member_role_ids))


def get_mode_label(mode: MentionMode) -> str:
    return "AND" if mode == "and" else "OR"


def format_selected_roles(selected_roles: list[discord.Role]) -> str:
    return " ".join(role.mention for role in selected_roles)


def format_member_preview(members: list[discord.Member]) -> str:
    if not members:
        return "対象となるメンバーが見つかりませんでした。"

    member_lines = [format_member_line(member) for member in members]
    return f"対象ユーザー: {len(members)} 人\n" + "\n".join(member_lines)


def format_member_line(member: discord.Member) -> str:
    return f"- {member.mention} ({member.display_name})"


def split_member_preview_messages(members: list[discord.Member]) -> list[str]:
    if not members:
        return []

    chunks = []
    current_lines = [f"対象ユーザー: {len(members)} 人"]

    for member in members:
        line = format_member_line(member)
        next_message = "\n".join([*current_lines, line])

        if len(next_message) > MAX_SELECTION_MESSAGE_LENGTH and len(current_lines) > 1:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


def build_selection_message(
    mode: MentionMode,
    selected_roles: list[discord.Role] | None = None,
    members: list[discord.Member] | None = None,
) -> str:
    lines = [
        f"{get_mode_label(mode)} 条件でメンションします。",
        "どのロールにメンションしますか？",
        "以下から複数選択してボタンを押してください。",
    ]

    if selected_roles is not None and members is not None:
        lines.extend(
            [
                "",
                f"選択中のロール: {format_selected_roles(selected_roles)}",
                format_member_preview(members),
            ]
        )

    return "\n".join(lines)


class MessageModal(discord.ui.Modal):
    def __init__(self, selected_roles: list[discord.Role], mode: MentionMode):
        super().__init__(title="メッセージを入力")
        self.selected_roles = selected_roles
        self.mode: MentionMode = mode
        self.message_input = discord.ui.TextInput(
            label="送信するメッセージ",
            style=discord.TextStyle.paragraph,
            placeholder="ここにメッセージを入力してください...",
            required=True,
            max_length=MAX_MESSAGE_INPUT_LENGTH,
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        mention_members = await get_target_members(
            interaction.guild, self.selected_roles, self.mode
        )
        if not mention_members:
            await interaction.followup.send(
                "対象となるメンバーが見つかりませんでした。", ephemeral=True
            )
            return

        mentions = " ".join(member.mention for member in mention_members)
        final_message = f"{mentions}\n\n{self.message_input.value or ''}"

        if len(final_message) > MAX_MESSAGE_LENGTH:
            await interaction.followup.send(
                f"メッセージが長すぎます({len(final_message)}文字)。",
                ephemeral=True,
            )
            return

        try:
            channel = interaction.channel
            if not isinstance(channel, discord.abc.Messageable):
                await interaction.followup.send(
                    "エラー: この場所にはメッセージを送信できません。",
                    ephemeral=True,
                )
                return

            await channel.send(final_message)
        except discord.Forbidden:
            await interaction.followup.send(
                "エラー: このチャンネルにメッセージを送信する権限がありません。",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"{len(mention_members)}人にメッセージを送信しました。",
            ephemeral=True,
        )


class RoleSelector(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="メンション対象のロールを選択 (複数可)",
            min_values=1,
            max_values=MAX_ROLES,
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, RoleSelectView):
            await interaction.response.defer()
            return

        view.selected_roles = list(self.values)
        await interaction.response.defer()
        mode = cast(MentionMode, view.mode)
        target_members = await get_target_members(
            interaction.guild, view.selected_roles, mode
        )
        selection_message = build_selection_message(
            mode, view.selected_roles, target_members
        )

        if len(selection_message) <= MAX_SELECTION_MESSAGE_LENGTH:
            await interaction.edit_original_response(
                content=selection_message,
                view=view,
            )
            return

        await interaction.edit_original_response(
            content="\n".join(
                [
                    f"{get_mode_label(cast(MentionMode, view.mode))} 条件でメンションします。",
                    "どのロールにメンションしますか？",
                    "対象ユーザーが多いため、一覧を分割して表示します。",
                    f"選択中のロール: {format_selected_roles(view.selected_roles)}",
                    f"対象ユーザー: {len(target_members)} 人",
                ]
            ),
            view=view,
        )

        for message in split_member_preview_messages(target_members):
            await interaction.followup.send(message, ephemeral=True)


class RoleSelectView(discord.ui.View):
    def __init__(self, mode: MentionMode):
        super().__init__(timeout=300)
        self.mode: MentionMode = mode
        self.selected_roles: list[discord.Role] = []
        self.add_item(RoleSelector())

    @discord.ui.button(
        label="メッセージ入力へ進む", style=discord.ButtonStyle.primary, row=1
    )
    async def proceed_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.selected_roles:
            await interaction.response.send_message(
                "ロールを1つ以上選択してください。",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            MessageModal(self.selected_roles, self.mode)
        )

        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        button.label = "送信処理中..."
        await interaction.edit_original_response(view=self)
        self.stop()


async def send_role_select_ui(interaction: discord.Interaction, mode: MentionMode):
    await interaction.response.send_message(
        build_selection_message(mode),
        view=RoleSelectView(mode),
        ephemeral=True,
    )


@tree.command(
    name="mention_and",
    description="選択したすべてのロールを持つユーザーにメンションします。",
)
async def mention_and(interaction: discord.Interaction):
    await send_role_select_ui(interaction, cast(MentionMode, "and"))


@tree.command(
    name="mention_or",
    description="選択したいずれかのロールを持つユーザーにメンションします。",
)
async def mention_or(interaction: discord.Interaction):
    await send_role_select_ui(interaction, cast(MentionMode, "or"))


@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot '{client.user}' が起動しました。")


try:
    client.run(os.environ["DISCORD_BOT_TOKEN"])
except KeyError:
    print("エラー: 環境変数 DISCORD_BOT_TOKEN が設定されていません。")
except discord.LoginFailure:
    print("エラー: Botトークンが不正です。")
