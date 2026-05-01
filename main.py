import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os

# =========================
# ⚙️ 配置
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_IDS = [
    801376018853134366,
    1087583384961830912,
    1274981048165335062,
    993734456550629396,
    1004674961060933672,
]

GUILDS = [discord.Object(id=g) for g in GUILD_IDS]
DB_PATH = "bot.db"

# =========================
# 🧱 数据库初始化（修正版，按服务器隔离）
# =========================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:

        # =========================
        # codes
        # =========================
        await db.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            game TEXT,
            code TEXT,
            used INTEGER DEFAULT 0
        )
        """)

        # =========================
        # claims
        # =========================
        await db.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            game TEXT,
            code TEXT
        )
        """)

        # =========================
        # games
        # =========================
        await db.execute("""
        CREATE TABLE IF NOT EXISTS games (
            guild_id INTEGER,
            name TEXT,
            PRIMARY KEY (guild_id, name)
        )
        """)

        # =========================
        # panel
        # =========================
        await db.execute("""
        CREATE TABLE IF NOT EXISTS panel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            title TEXT,
            message_id INTEGER,
            channel_id INTEGER,
            hidden INTEGER DEFAULT 0
        )
        """)

        # =========================
        # panel_buttons
        # =========================
        await db.execute("""
        CREATE TABLE IF NOT EXISTS panel_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            message_id INTEGER,
            channel_id INTEGER,
            label TEXT,
            custom_id TEXT,
            hidden INTEGER DEFAULT 0
        )
        """)

        # =========================
        # dm_text
        # =========================
        await db.execute("""
        CREATE TABLE IF NOT EXISTS dm_text (
            guild_id INTEGER,
            game TEXT,
            text TEXT,
            PRIMARY KEY (guild_id, game)
        )
        """)

        await db.commit()

# =========================
# 🎮 游戏列表
# =========================
async def get_games(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name FROM games WHERE guild_id=?", (guild_id,)) as c:
            rows = await c.fetchall()
            return [r[0] for r in rows]

# =========================
# ⚡ Admin Check
# =========================
def admin_only(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

# =========================
# Start View
# =========================
class StartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎁 Claim Your Code",
        style=discord.ButtonStyle.green,
        custom_id="start_btn"
    )
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id  # 获取当前服务器ID
        games = await get_games(guild_id)  # 按服务器获取游戏
        if not games:
            await interaction.response.send_message(
                "❌ No games available for this server.", 
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            "🎮 Choose your game:", 
            view=GameView(games), 
            ephemeral=True
        )

# =========================
# Game View
# =========================
class GameView(discord.ui.View):
    def __init__(self, games):
        super().__init__(timeout=60)
        self.add_item(GameSelect(games))

# =========================
# 🧠 Persistent Start Button View（必须在 Bot 前）
# =========================
class PersistentStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(discord.ui.Button(
            label="🎁 Claim Your Code",
            style=discord.ButtonStyle.green,
            custom_id="start_btn"
        ))

# =========================
# 🆕 Bot 启动
# =========================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 初始化数据库
        await init_db()
        # 注册 persistent view
        self.add_view(StartView())

        # 只同步指定服务器的 slash commands
        for guild_id in GUILD_IDS:
            guild = discord.Object(id=guild_id)
            try:
                synced = await self.tree.sync(guild=guild)
                print(f"Synced {len(synced)} commands for guild {guild_id}")
            except Exception as e:
                print(f"Failed to sync commands for guild {guild_id}: {e}")

    async def on_ready(self):
        print(f"Bot ready: {self.user}")

# =========================
# 🚀 创建 bot（必须在最后）
# =========================
bot = MyBot()

# =========================
# 🆕 /add_game
# =========================
@bot.tree.command(
    name="add_game",
    description="Add a new game",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def add_game(interaction: discord.Interaction, name: str):
    guild_id = interaction.guild.id  # ⚡ 获取当前服务器 ID
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO games (guild_id, name) VALUES (?, ?)",
            (guild_id, name)
        )
        await db.commit()  # 提交事务

    await interaction.response.send_message(
        f"✅ Game added: {name} for this server.",
        ephemeral=True
    )

# =========================
# 🎁 上传礼品码（按服务器隔离）
# =========================
class UploadModal(discord.ui.Modal, title="Upload Game Codes"):
    codes_text = discord.ui.TextInput(
        label="Enter codes (one per line)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    def __init__(self, guild_id: int, game: str):
        super().__init__(custom_id=f"upload_modal_{guild_id}_{game}")
        self.guild_id = guild_id
        self.game = game

    async def on_submit(self, interaction: discord.Interaction):
        codes = [line.strip() for line in self.codes_text.value.splitlines() if line.strip()]
        count = 0
        async with aiosqlite.connect(DB_PATH) as db:
            for code in codes:
                await db.execute(
                    "INSERT INTO codes (guild_id, game, code) VALUES (?, ?, ?)",
                    (self.guild_id, self.game, code)
                )
                count += 1
            await db.commit()
        await interaction.response.send_message(
            f"✅ Uploaded {count} codes for **{self.game}**",
            ephemeral=True
        )

class UploadSelect(discord.ui.Select):
    def __init__(self, guild_id: int, games: list[str]):
        self.guild_id = guild_id
        options = [discord.SelectOption(label=g) for g in games]
        super().__init__(placeholder="Choose a game to upload codes", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UploadModal(self.guild_id, self.values[0]))

class UploadView(discord.ui.View):
    def __init__(self, guild_id: int, games: list[str]):
        super().__init__(timeout=60)
        self.add_item(UploadSelect(guild_id, games))

@bot.tree.command(
    name="upload",
    description="Upload codes for a game",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def upload(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    games = await get_games(guild_id)
    if not games:
        await interaction.response.send_message(
            "❌ No games added yet for this server.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Select a game to upload codes:",
        view=UploadView(guild_id, games),
        ephemeral=True
    )

# =========================
# 📦 /stock 显示未使用库存（按服务器隔离）
# =========================
@bot.tree.command(
    name="stock",
    description="Check stock of codes",
    guilds=GUILDS
)
async def stock(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    async with aiosqlite.connect(DB_PATH) as db:
        # 查询该服务器的游戏列表
        async with db.execute("SELECT name FROM games WHERE guild_id=?", (guild_id,)) as c:
            games = await c.fetchall()

        if not games:
            await interaction.response.send_message(
                "📦 No games found for this server.",
                ephemeral=True
            )
            return

        msg = "📦 Stock (unused codes) for this server:\n"

        # 查询每个游戏的库存
        for g, in games:
            async with db.execute(
                "SELECT COUNT(*) FROM codes WHERE guild_id=? AND game=? AND used=0",
                (guild_id, g)
            ) as c2:
                count = (await c2.fetchone())[0]
            msg += f"{g}: {count}\n"

    await interaction.response.send_message(msg, ephemeral=True)

# =========================
# 📊 /claim_history 显示已领取记录（按服务器隔离）
# =========================
@bot.tree.command(
    name="claim_history",
    description="View claim history",
    guilds=GUILDS
)
async def claim_history(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    async with aiosqlite.connect(DB_PATH) as db:
        # 查询该服务器领取记录
        async with db.execute(
            "SELECT game, COUNT(*) FROM claims WHERE guild_id=? GROUP BY game",
            (guild_id,)
        ) as c:
            rows = await c.fetchall()

    if not rows:
        msg = "📊 No claims yet for this server."
    else:
        msg = "📊 Claims (codes successfully sent via DM) for this server:\n"
        for g, c_count in rows:
            msg += f"{g}: {c_count}\n"

    await interaction.response.send_message(msg, ephemeral=True)

# =========================
# ♻️ /reset（CSV + 统计版，按服务器隔离）
# =========================
import io
import csv
from datetime import datetime

@bot.tree.command(
    name="reset",
    description="Reset all codes and claims (with backup, this server only)",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def reset(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild.id

    # ===== 读取领取记录 =====
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, game, code FROM claims WHERE guild_id=?",
            (guild_id,)
        ) as c:
            rows = await c.fetchall()

        # 同时统计每个游戏领取人数
        async with db.execute(
            "SELECT game, COUNT(*) FROM claims WHERE guild_id=? GROUP BY game",
            (guild_id,)
        ) as c2:
            stats = await c2.fetchall()

    # ===== 生成 CSV =====
    if rows:
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([])
        writer.writerow(["--- Summary ---"])
        writer.writerow(["Game", "ClaimCount"])
        for game, count in stats:
            writer.writerow([game, count])

        file_content = output.getvalue()
        file = discord.File(
            fp=io.BytesIO(file_content.encode("utf-8-sig")),
            filename=f"claim_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    else:
        file = None

    # ===== 执行重置 =====
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM claims WHERE guild_id=?", (guild_id,))
        await db.execute("DELETE FROM codes WHERE guild_id=?", (guild_id,))
        await db.commit()

    # ===== 返回结果 =====
    if file:
        await interaction.followup.send(
            content="♻️ Reset completed for this server. CSV backup with stats attached.",
            file=file,
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "♻️ Reset completed for this server. No claim history to backup.",
            ephemeral=True
        )

# =========================
# 🎁 获取礼品码（优化 DM 逻辑）
# =========================
async def handle_claim(interaction, game):
    user = interaction.user

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")

        # 1️⃣ 防重复领取
        async with db.execute(
            "SELECT 1 FROM claims WHERE guild_id=? AND user_id=? AND game=?",
            (interaction.guild.id, user.id, game)
        ) as c:
            if await c.fetchone():
                await db.rollback()
                await interaction.response.send_message(
                    "⚠️ You have already claimed the code for this game this month.",
                    ephemeral=True
                )
                return

        # 2️⃣ 原子抢码（关键防并发）
        async with db.execute(
            """
            SELECT id, code
            FROM codes
            WHERE guild_id=? AND game=? AND used=0
            LIMIT 1
            """,
            (interaction.guild.id, game)
        ) as c:
            row = await c.fetchone()

        if not row:
            await db.rollback()
            await interaction.response.send_message(
                "❌ Out of stock.",
                ephemeral=True
            )
            return

        code_id, code = row

        # 3️⃣ 标记已使用 + 写记录
        await db.execute(
            "UPDATE codes SET used=1 WHERE id=?",
            (code_id,)
        )

        await db.execute(
            "INSERT INTO claims (guild_id, user_id, game, code) VALUES (?, ?, ?, ?)",
            (interaction.guild.id, user.id, game, code)
        )

        await db.commit()

    # ===== DM =====
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT text FROM dm_text WHERE guild_id=? AND game=?",
            (interaction.guild.id, game)
        ) as c:
            row = await c.fetchone()

    if row:
        dm_text = row[0].replace("{code}", code)
    else:
        dm_text = f"🎁 Your {game} code:\n`{code}`"

    try:
        await user.send(dm_text)

    except discord.Forbidden:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE codes SET used=0 WHERE id=?",
                (code_id,)
            )
            await db.execute(
                "DELETE FROM claims WHERE guild_id=? AND user_id=? AND game=?",
                (interaction.guild.id, user.id, game)
            )
            await db.commit()

        await interaction.response.send_message(
            "⚠️ Cannot send DM. Please enable DM.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "✅ Code sent to your DM!",
        ephemeral=True
    )

# =========================
# 🎮 下拉菜单与按钮（优化领取逻辑）
# =========================

class GameSelect(discord.ui.Select):
    def __init__(self, games):
        options = [discord.SelectOption(label=g) for g in games]
        super().__init__(placeholder="Choose your game", options=options)

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]

        # ✅ 只保留这一行
        await handle_claim(interaction, game)

# =========================
# 📝 /post
# =========================
@bot.tree.command(
    name="post",
    description="Post a new panel",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def post(interaction: discord.Interaction):
    await interaction.response.send_modal(PostModal())

# =========================
# 📝 Modal
# =========================
class PostModal(discord.ui.Modal, title="Post New Panel"):

    def __init__(self):
        super().__init__(custom_id="post_modal")

        # 创建 TextInput
        self.title_text = discord.ui.TextInput(label="Admin Title", required=True)
        self.image_url = discord.ui.TextInput(label="Image URL", required=False)
        self.content_text = discord.ui.TextInput(
            label="Message Content",
            style=discord.TextStyle.paragraph,
            required=True
        )

        # ⚠️ 必须加这一步
        self.add_item(self.title_text)
        self.add_item(self.image_url)
        self.add_item(self.content_text)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(description=self.content_text.value)

        if self.image_url.value:
            embed.set_image(url=self.image_url.value)

        # =========================
        # UI
        # =========================
        view = StartView()

        msg = await interaction.channel.send(embed=embed, view=view)

        async with aiosqlite.connect(DB_PATH) as db:

            # =========================
            # panel
            # =========================
            await db.execute(
                "INSERT INTO panel (title, message_id, channel_id) VALUES (?, ?, ?)",
                (self.title_text.value, msg.id, interaction.channel.id)
            )

            # =========================
            # 清旧按钮（防重复）
            # =========================
            await db.execute(
                "DELETE FROM panel_buttons WHERE message_id=?",
                (msg.id,)
            )

            # =========================
            # 存 Start 按钮（稳定写法）
            # =========================
            await db.execute("""
                INSERT INTO panel_buttons (
                    message_id,
                    channel_id,
                    label,
                    custom_id
                ) VALUES (?, ?, ?, ?)
            """, (
                msg.id,
                interaction.channel.id,
                "🎁 Claim Your Code",
                "start_btn"
            ))

            await db.commit()

        await interaction.response.send_message(
            "✅ Panel posted successfully",
            ephemeral=True
        )

# =========================
# 1️⃣ MODAL（必须最上面）
# =========================
class EditPostModal(discord.ui.Modal, title="Edit Panel"):
    def __init__(self, title, message_id, channel_id, old_content, old_url):
        # ⚠️ 给 Modal 设置 custom_id 保证唯一
        super().__init__(custom_id=f"edit_post_modal_{message_id}")

        self.title = title
        self.message_id = message_id
        self.channel_id = channel_id

        # 每个实例都新建 TextInput
        self.content_text = discord.ui.TextInput(
            label="Message Content",
            style=discord.TextStyle.paragraph,
            required=True,
            default=old_content
        )

        self.image_url = discord.ui.TextInput(
            label="Image URL",
            required=False,
            default=old_url
        )

        # 添加到 Modal
        self.add_item(self.content_text)
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.client.get_channel(self.channel_id)
        if channel is None:
            channel = await interaction.client.fetch_channel(self.channel_id)

        msg = await channel.fetch_message(self.message_id)

        embed = discord.Embed(description=self.content_text.value)

        if self.image_url.value:
            embed.set_image(url=self.image_url.value)

        await msg.edit(embed=embed, view=StartView())

        await interaction.response.send_message(
            f"✅ Panel '{self.title}' updated.",
            ephemeral=True
        )

# =========================
# 2️⃣ SELECT
# =========================
class EditPostSelect(discord.ui.Select):
    def __init__(self, panels):
        options = [
            discord.SelectOption(label=p[0], value=str(p[1]))
            for p in panels
        ]

        super().__init__(
            placeholder="Select a panel to edit",
            options=options
        )

        self.panels = {
            str(p[1]): (p[0], p[2])
            for p in panels
        }

    async def callback(self, interaction: discord.Interaction):
        message_id = self.values[0]
        title, channel_id = self.panels[message_id]

        channel = interaction.client.get_channel(channel_id)
        if channel is None:
            channel = await interaction.client.fetch_channel(channel_id)

        msg = await channel.fetch_message(int(message_id))

        old_content = msg.embeds[0].description if msg.embeds else ""
        old_url = msg.embeds[0].image.url if msg.embeds and msg.embeds[0].image else ""

        await interaction.response.send_modal(
            EditPostModal(title, int(message_id), channel_id, old_content, old_url)
        )

# =========================
# 3️⃣ VIEW
# =========================
class EditPostView(discord.ui.View):
    def __init__(self, panels):
        super().__init__(timeout=60)
        self.add_item(EditPostSelect(panels))

# =========================
# 4️⃣ COMMAND
# =========================
@bot.tree.command(
    name="edit_post",
    description="Edit an existing panel",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def edit_post(interaction: discord.Interaction):

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title, message_id, channel_id FROM panel WHERE hidden=0"
        ) as c:
            panels = await c.fetchall()

    if not panels:
        await interaction.response.send_message(
            "❌ No panels found.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Select a panel to edit:",
        view=EditPostView(panels),
        ephemeral=True
    )

    async with aiosqlite.connect(DB_PATH) as db:

        # =========================
        # 🧹 清旧备份
        # =========================
        await db.execute(
            "DELETE FROM panel_buttons WHERE message_id=?",
            (message_id,)
        )

        # =========================
        # 💾 备份按钮
        # =========================
        for row in msg.components:
            for item in row.children:

                if getattr(item, "type", None) == discord.ComponentType.button:

                    await db.execute("""
                        INSERT INTO panel_buttons (
                            message_id,
                            channel_id,
                            label,
                            custom_id
                        )
                        VALUES (?, ?, ?, ?)
                    """, (
                        message_id,
                        channel_id,
                        item.label,
                        item.custom_id
                    ))

        await db.commit()

    # =========================
    # ❌ 移除 UI
    # =========================
    await msg.edit(view=None)

    await interaction.response.send_message(
        f"✅ Buttons removed from '{title}'",
        ephemeral=True
    )

# =========================
# remove button select
# =========================
class RemoveButtonSelect(discord.ui.Select):

    def __init__(self, panels):

        self.panels = {
            str(p[1]): (p[0], p[2])
            for p in panels
        }

        options = [
            discord.SelectOption(label=p[0], value=str(p[1]))
            for p in panels
        ]

        super().__init__(
            placeholder="Select panel",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        message_id = int(self.values[0])

        title, channel_id = self.panels[str(message_id)]

        channel = await interaction.client.fetch_channel(channel_id)
        msg = await channel.fetch_message(message_id)

        async with aiosqlite.connect(DB_PATH) as db:

            # backup buttons
            await db.execute(
                "DELETE FROM panel_buttons WHERE message_id=?",
                (message_id,)
            )

            for row in msg.components:
                for item in row.children:

                    if getattr(item, "type", None) == discord.ComponentType.button:

                        await db.execute("""
                            INSERT INTO panel_buttons (
                                message_id,
                                channel_id,
                                label,
                                custom_id
                            )
                            VALUES (?, ?, ?, ?)
                        """, (
                            message_id,
                            channel_id,
                            item.label,
                            item.custom_id
                        ))

            await db.commit()

        await msg.edit(view=None)

        await interaction.response.send_message(
            f"✅ Buttons removed from '{title}'",
            ephemeral=True
        )

# =========================
# remove button view
# =========================
class RemoveButtonView(discord.ui.View):
    def __init__(self, panels):
        super().__init__(timeout=60)
        self.add_item(RemoveButtonSelect(panels))

# =========================
# /remove_button
# =========================
@bot.tree.command(
    name="remove_button",
    description="Remove buttons from a panel",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def remove_button(interaction: discord.Interaction):

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title, message_id, channel_id FROM panel WHERE hidden=0"
        ) as c:
            panels = await c.fetchall()

    if not panels:
        await interaction.response.send_message(
            "❌ No panels",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Select panel:",
        view=RemoveButtonView(panels),
        ephemeral=True
    )

# =========================
# restore button select
# =========================
class RestoreButtonSelect(discord.ui.Select):

    def __init__(self, panels):

        self.panels = {
            str(p[1]): (p[0], p[2])
            for p in panels
        }

        options = [
            discord.SelectOption(label=p[0], value=str(p[1]))
            for p in panels
        ]

        super().__init__(
            placeholder="Select panel",
            options=options
        )

    # ✅ 注意：必须缩进在 class 里面
    async def callback(self, interaction: discord.Interaction):

        message_id = int(self.values[0])

        if str(message_id) not in self.panels:
            await interaction.response.send_message(
                "❌ Panel not found",
                ephemeral=True
            )
            return

        title, channel_id = self.panels[str(message_id)]

        channel = await interaction.client.fetch_channel(channel_id)
        msg = await channel.fetch_message(message_id)

        await msg.edit(view=StartView())

        await interaction.response.send_message(
            f"✅ Restored panel '{title}'",
            ephemeral=True
        )

# =========================
# restore view
# =========================

class RestoreButtonView(discord.ui.View):
    def __init__(self, panels):
        super().__init__(timeout=60)
        self.add_item(RestoreButtonSelect(panels))

@bot.tree.command(
    name="restore_button",
    description="Restore buttons to a panel",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def restore_button(interaction: discord.Interaction):

    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute("""
            SELECT title, message_id, channel_id
            FROM panel
            WHERE hidden=0
        """) as c:
            rows = await c.fetchall()

    if not rows:
        await interaction.response.send_message(
            "❌ No panels found",
            ephemeral=True
        )
        return

    view = RestoreButtonView(rows)

    await interaction.response.send_message(
        "Select panel to restore:",
        view=view,
        ephemeral=True
    )

# =========================
# /edit DM
# =========================
class EditDMSelect(discord.ui.Select):
    def __init__(self, games):
        options = [discord.SelectOption(label=g) for g in games]
        super().__init__(placeholder="Select a game to edit DM text", options=options)

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]
        guild_id = interaction.guild.id
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT text FROM dm_text WHERE guild_id=? AND game=?",
                (guild_id, game)
            ) as c:
                row = await c.fetchone()
        old_text = row[0] if row else "{code}"
        await interaction.response.send_modal(EditDMModal(game, old_text))

class EditDMModal(discord.ui.Modal, title="Edit DM Text"):
    def __init__(self, game, old_text):
        # ⚠️ 给每个 Modal 一个唯一 custom_id
        super().__init__(custom_id=f"edit_dm_modal_{game}")

        self.game = game

        # 创建实例化的 TextInput
        self.text_input = discord.ui.TextInput(
            label="DM Text",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
            default=old_text
        )

        # 添加到 Modal
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO dm_text (guild_id, game, text) VALUES (?, ?, ?)",
                (guild_id, self.game, self.text_input.value)
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ DM text for '{self.game}' updated for this server.",
            ephemeral=True
        )

class EditDMView(discord.ui.View):
    def __init__(self, games):
        super().__init__(timeout=60)
        self.add_item(EditDMSelect(games))

@bot.tree.command(
    name="edit_dm",
    description="Edit DM text for a game",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def edit_dm(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    games = await get_games(guild_id)  # ⚠️ 这里传入 guild_id
    if not games:
        await interaction.response.send_message("❌ No games found.", ephemeral=True)
        return

    await interaction.response.send_message(
        "Select a game to edit DM text:",
        view=EditDMView(games),
        ephemeral=True
    )

# =========================
# 🎁 编辑未使用的礼品码（按服务器隔离）
# =========================
class EditCodesModal(discord.ui.Modal, title="Edit Unused Codes"):
    codes_text = discord.ui.TextInput(
        label="Edit codes (one per line)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    def __init__(self, game: str):
        super().__init__()
        self.game = game

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id  # ⚠️ 加上 guild_id
        new_codes = [line.strip() for line in self.codes_text.value.splitlines() if line.strip()]
        async with aiosqlite.connect(DB_PATH) as db:
            # 删除该服务器该游戏所有未使用的代码
            await db.execute(
                "DELETE FROM codes WHERE guild_id=? AND game=? AND used=0",
                (guild_id, self.game)
            )
            # 插入新的代码
            for code in new_codes:
                await db.execute(
                    "INSERT INTO codes (guild_id, game, code) VALUES (?, ?, ?)",
                    (guild_id, self.game, code)
                )
            await db.commit()
        await interaction.response.send_message(
            f"✅ Updated {len(new_codes)} unused codes for **{self.game}** in this server",
            ephemeral=True
        )

class EditCodesSelect(discord.ui.Select):
    def __init__(self, games):
        options = [discord.SelectOption(label=g) for g in games]
        super().__init__(placeholder="Select a game to edit codes", options=options)

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]
        guild_id = interaction.guild.id
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT code FROM codes WHERE guild_id=? AND game=? AND used=0",
                (guild_id, game)
            ) as c:
                rows = await c.fetchall()
        codes_text = "\n".join(r[0] for r in rows)
        modal = EditCodesModal(game)
        modal.codes_text.default = codes_text
        await interaction.response.send_modal(modal)

class EditCodesView(discord.ui.View):
    def __init__(self, games):
        super().__init__(timeout=60)
        self.add_item(EditCodesSelect(games))


@bot.tree.command(
    name="edit_codes",
    description="Edit unused codes for a game",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def edit_codes(interaction: discord.Interaction):
    guild_id = interaction.guild.id  # ⚠️ 传入当前服务器
    games = await get_games(guild_id)
    if not games:
        await interaction.response.send_message("❌ No games added yet.", ephemeral=True)
        return
    await interaction.response.send_message(
        "Select a game to edit codes:",
        view=EditCodesView(games),
        ephemeral=True
    )

# =========================
# 🆕 /hide_panel
# =========================
@bot.tree.command(
    name="hide_panel",
    description="Hide a panel from edit list",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def hide_panel(interaction: discord.Interaction, message_id: str):
    guild_id = interaction.guild.id  # 当前服务器 ID

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE panel SET hidden=1 WHERE guild_id=? AND message_id=?",
            (guild_id, message_id)
        )
        await db.commit()

    await interaction.response.send_message(
        "✅ Panel hidden (not deleted) for this server.",
        ephemeral=True
    )

# =========================
# 🆕 /unhide_panel
# =========================
@bot.tree.command(
    name="unhide_panel",
    description="Restore hidden panels back to lists",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def unhide_panel(interaction: discord.Interaction):
    guild_id = interaction.guild.id  # 当前服务器 ID

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title, message_id, channel_id FROM panel WHERE hidden=1 AND guild_id=?",
            (guild_id,)
        ) as c:
            panels = await c.fetchall()

    if not panels:
        await interaction.response.send_message(
            "❌ No hidden panels found for this server.",
            ephemeral=True
        )
        return

    view = UnhidePanelView(panels)

    await interaction.response.send_message(
        "Select a panel to restore:",
        view=view,
        ephemeral=True
    )

# =========================
# 🆕 /remove_game Select 类
# =========================
class DeleteGameSelect(discord.ui.Select):
    def __init__(self, games, guild_id: int):
        super().__init__(placeholder="Select a game to delete", options=[discord.SelectOption(label=g) for g in games])
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM games WHERE guild_id=? AND name=?",
                (self.guild_id, game)
            )
            await db.execute(
                "DELETE FROM codes WHERE guild_id=? AND game=?",
                (self.guild_id, game)
            )
            await db.commit()

        await interaction.response.send_message(
            f"✅ Game **{game}** deleted from this server.",
            ephemeral=True
        )

# =========================
# 🆕 /remove_game 命令
# =========================
@bot.tree.command(
    name="remove_game",
    description="Delete a game",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def delete_game(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    games = await get_games(guild_id)
    if not games:
        await interaction.response.send_message("❌ No games found.", ephemeral=True)
        return

    view = discord.ui.View()
    view.add_item(DeleteGameSelect(games, guild_id=guild_id))
    await interaction.response.send_message(
        "Select a game to delete:",
        view=view,
        ephemeral=True
    )

# =========================
# 🆕 /user_claim_records
# =========================
@bot.tree.command(
    name="user_claim_records",
    description="Check user's claimed codes",
    guilds=GUILDS
)
@app_commands.check(admin_only)
async def user_claim_records(interaction: discord.Interaction, user: discord.User):
    guild_id = interaction.guild.id  # 当前服务器

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT game, code FROM claims WHERE guild_id=? AND user_id=?",
            (guild_id, user.id)
        ) as c:
            rows = await c.fetchall()

    if not rows:
        await interaction.response.send_message(
            f"❌ {user.display_name} has no claimed codes in this server.",
            ephemeral=True
        )
        return

    msg = f"📊 {user.display_name}'s claimed codes in this server:\n" + "".join(
        f"{g}: {c}\n" for g, c in rows
    )

    await interaction.response.send_message(msg, ephemeral=True)

# =========================
# 🟢 Bot ready
# =========================
@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user}")

bot.run(TOKEN)
