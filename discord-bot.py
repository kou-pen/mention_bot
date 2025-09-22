import discord
import typing

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

class MessageModal(discord.ui.Modal):
    def __init__(self, selected_roles: list[discord.Role]):
        super().__init__(title="メッセージを入力")
        self.selected_roles = selected_roles

    message_input = discord.ui.TextInput(
        label="送信するメッセージ",
        style=discord.TextStyle.paragraph,
        placeholder="ここにメッセージを入力してください...",
        required=True,
        max_length=1500,  
    )

    async def on_submit(self, interaction: discord.Interaction):

        await interaction.response.defer(ephemeral=True, thinking=True)

        target_roles_set = set(self.selected_roles)
        mention_members = []

        for member in interaction.guild.members:
            if member.bot:
                continue
            
            if target_roles_set.issubset(set(member.roles)):
                mention_members.append(member)

        if not mention_members:
            await interaction.followup.send("対象となるメンバーが見つかりませんでした。", ephemeral=True)
            return

        mentions_str = ' '.join(m.mention for m in mention_members)
        final_message = f"{mentions_str}\n\n{self.message_input.value}"

        if len(final_message) > 2000:
            await interaction.followup.send(f"メッセージが長すぎます({len(final_message)}文字)。", ephemeral=True)
            return

        try:
            await interaction.channel.send(final_message)
        except discord.errors.Forbidden:
            await interaction.followup.send("エラー: このチャンネルにメッセージを送信する権限がありません。", ephemeral=True)
            return
            
        await interaction.followup.send(f"✅ {len(mention_members)}人にメッセージを送信しました。", ephemeral=True)

class MessageModal(discord.ui.Modal):
    def __init__(self, selected_roles: list[discord.Role]):
        super().__init__(title="メッセージを入力")
        self.selected_roles = selected_roles

    message_input = discord.ui.TextInput(
        label="送信するメッセージ",
        style=discord.TextStyle.paragraph,
        placeholder="ここにメッセージを入力してください...",
        required=True,
        max_length=1500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        target_roles_set = set(self.selected_roles)
        mention_members = [
            member for member in interaction.guild.members
            if not member.bot and target_roles_set.issubset(set(member.roles))
        ]

        if not mention_members:
            await interaction.followup.send("対象となるメンバーが見つかりませんでした。", ephemeral=True)
            return

        mentions_str = ' '.join(m.mention for m in mention_members)
        final_message = f"{mentions_str}\n\n{self.message_input.value}"

        if len(final_message) > 2000:
            await interaction.followup.send(f"メッセージが長すぎます({len(final_message)}文字)。", ephemeral=True)
            return

        try:
            await interaction.channel.send(final_message)
            await interaction.followup.send(f"✅ {len(mention_members)}人にメッセージを送信しました。", ephemeral=True)
        except discord.errors.Forbidden:
            await interaction.followup.send("エラー: このチャンネルにメッセージを送信する権限がありません。", ephemeral=True)


class RoleSelector(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="メンション対象のロールを選択 (複数可)",
            min_values=1,
            max_values=10,
        )

    async def callback(self, interaction: discord.Interaction):

        self.view.selected_roles = self.values
        await interaction.response.defer()

class RoleSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.selected_roles = []
        self.add_item(RoleSelector())

    @discord.ui.button(label="メッセージ入力へ進む", style=discord.ButtonStyle.primary, row=1)
    async def proceed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_roles:
            await interaction.response.send_message("⚠️ ロールを1つ以上選択してください。", ephemeral=True)
            return
        
        modal = MessageModal(self.selected_roles)
        await interaction.response.send_modal(modal)
        
        self.stop()
        for item in self.children:
            item.disabled = True
        button.label = "送信処理中..."
        
        await interaction.edit_original_response(view=self)

@tree.command(name="mention_ui", description="UIを使ってメンション付きメッセージを送信します。")
async def mention_ui(interaction: discord.Interaction):
    view = RoleSelectView()
    await interaction.response.send_message(
        "どのロールにメンションしますか？\n以下から複数選択してボタンを押してください。",
        view=view,
        ephemeral=True
    )

@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot '{client.user}' が起動しました。")

try:

    import os
    client.run(os.environ['DISCORD_BOT_TOKEN'])
except discord.errors.LoginFailure:
    print("エラー: Botトークンが不正です。")
