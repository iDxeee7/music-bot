import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
from flask import Flask
from threading import Thread

# ----------------- 1. خادم Flask لإبقاء البوت أونلاين -----------------
app = Flask('')

@app.route('/')
def home():
    return "Music Bot 24/7 is Running!"

def run():
    # استخدام البورت المخصص ديناميكياً من Render
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ----------------- 2. إعدادات البوت والـ Slash Commands -----------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# قوائم التشغيل لكل سيرفر
queues = {}

# إعدادات yt-dlp مع إجبار IPv4 لتجاوز حظر يوتيوب على Render
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',  # إجبار الاتصال عبر IPv4 لتفادي تعليق يوتيوب
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# ----------------- 3. واجهة الأزرار التفاعلية (Buttons UI) -----------------
class MusicControlView(discord.ui.View):
    def __init__(self, ctx_or_interaction):
        super().__init__(timeout=None)
        self.target = ctx_or_interaction

    @discord.ui.button(label="⏸️ إيقاف مؤقت / استئناف", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message("البوت ليس في روم صوتي!", ephemeral=True)
        
        if vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ تم استئناف التشغيل.", ephemeral=True)
        elif vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ تم الإيقاف المؤقت.", ephemeral=True)
        else:
            await interaction.response.send_message("لا يوجد شيء يعمل حالياً.", ephemeral=True)

    @discord.ui.button(label="⏭️ تخطي", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ تم تخطي المقطع.", ephemeral=True)
        else:
            await interaction.response.send_message("لا يوجد شيء لتخطيه.", ephemeral=True)

    @discord.ui.button(label="⏹️ إيقاف شامل", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        if guild_id in queues:
            queues[guild_id].clear()
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await interaction.response.send_message("⏹️ تم إيقاف التشغيل وتفريغ قائمة الانتظار.", ephemeral=True)
        else:
            await interaction.response.send_message("البوت غير متصل.", ephemeral=True)

# ----------------- 4. دالة تشغيل القائمة المتتابعة -----------------
def play_next(guild_id, interaction_or_channel):
    if guild_id in queues and len(queues[guild_id]) > 0:
        song = queues[guild_id].pop(0)
        vc = song['vc']
        
        player = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)
        vc.play(player, after=lambda e: play_next(guild_id, interaction_or_channel))
        
        embed = discord.Embed(title="🎵 جاري التشغيل الآن", description=f"[{song['title']}]({song['link']})", color=discord.Color.green())
        embed.add_field(name="المدة / المنصة", value=song.get('duration', 'غير معروف'))
        
        asyncio.run_coroutine_threadsafe(
            song['channel'].send(embed=embed, view=MusicControlView(song['channel'])),
            bot.loop
        )

# ----------------- 5. الأوامر ومزامنة الـ Slash -----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'✅ البوت جاهز ويعمل باسم: {bot.user.name}')

# --- أمر التشغيل /p ---
@bot.tree.command(name="p", description="تشغيل أغنية من يوتيوب، سبوتيفاي، ساوندكلاود أو بالبحث")
@app_commands.describe(query="رابط أو اسم الأغنية")
async def play_slash(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send("❌ يرجى الدخول إلى روم صوتي أولاً!")

    voice_channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    try:
        if vc is None:
            vc = await voice_channel.connect()
        elif vc.channel.id != voice_channel.id:
            await vc.move_to(voice_channel)
    except discord.errors.Forbidden:
        return await interaction.followup.send("❌ ليس لدي صلاحية للاتصال بالروم الصوتي الخاص بك!")
    except Exception as e:
        return await interaction.followup.send(f"❌ تعذر الاتصال بالروم: {str(e)}")

    guild_id = interaction.guild.id
    if guild_id not in queues:
        queues[guild_id] = []

    loop = asyncio.get_event_loop()
    search_target = query if query.startswith("http") else f"ytsearch:{query}"
    
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_target, download=False))
    except Exception as e:
        return await interaction.followup.send(f"❌ تعذر العثور على المقطع أو التشغيل: {str(e)}")

    if 'entries' in data and data['entries']:
        data = data['entries'][0]

    song_info = {
        'url': data['url'],
        'title': data.get('title', 'مقطع صوتي'),
        'link': data.get('webpage_url', query),
        'duration': f"{data.get('duration', 0)} ثانية",
        'vc': vc,
        'channel': interaction.channel
    }

    if vc.is_playing() or vc.is_paused():
        queues[guild_id].append(song_info)
        embed = discord.Embed(title="📝 تم الإضافة إلى قائمة الانتظار", description=f"[{song_info['title']}]({song_info['link']})", color=discord.Color.blue())
        await interaction.followup.send(embed=embed)
    else:
        queues[guild_id].append(song_info)
        play_next(guild_id, interaction.channel)
        await interaction.followup.send("🎶 جاري إعداد وتكليف التشغيل...")

# --- أمر التخطي /s ---
@bot.tree.command(name="s", description="تخطي الأغنية الحالية")
async def skip_slash(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("⏭️ تم تخطي المقطع.")
    else:
        await interaction.response.send_message("❌ لا يوجد شيء لتخطيه حالياً.")

# --- أمر الإيقاف /stop ---
@bot.tree.command(name="stop", description="إيقاف التشغيل تماماً وتفريغ القائمة")
async def stop_slash(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in queues:
        queues[guild_id].clear()
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        await interaction.response.send_message("⏹️ تم الإيقاف وتفريغ قائمة الانتظار.")
    else:
        await interaction.response.send_message("❌ البوت ليس متصلاً بأي روم.")

# ----------------- 6. تشغيل الخادم والبوت -----------------
keep_alive()

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)