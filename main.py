import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
from flask import Flask
from threading import Thread

# ----------------- 1. خادم Flask لإبقاء البوت أونلاين 24/7 -----------------
app = Flask('')

@app.route('/')
def home():
    return "Music Bot 24/7 is Running!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ----------------- 2. إعدادات البوت والـ YTDL -----------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

queues = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web', 'ios'],
            'skip': ['hls', 'dash']
        }
    }
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

def format_duration(seconds):
    try:
        seconds = int(float(seconds))
        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
    except:
        return "غير معروف"

# ----------------- 3. واجهة الأزرار التفاعلية العصرية -----------------
class MusicControlView(discord.ui.View):
    def __init__(self, ctx_or_interaction):
        super().__init__(timeout=None)
        self.target = ctx_or_interaction

    @discord.ui.button(label="⏸️ إيقاف / استئناف", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.followup.send("❌ البوت ليس في روم صوتي!", ephemeral=True)
        
        if vc.is_paused():
            vc.resume()
            await interaction.followup.send("▶️ تم استئناف التشغيل.", ephemeral=True)
        elif vc.is_playing():
            vc.pause()
            await interaction.followup.send("⏸️ تم الإيقاف المؤقت.", ephemeral=True)
        else:
            await interaction.followup.send("❌ لا يوجد شيء يعمل حالياً.", ephemeral=True)

    @discord.ui.button(label="⏭️ تخطي", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.followup.send("⏭️ تم تخطي المقطع.", ephemeral=True)
        else:
            await interaction.followup.send("❌ لا يوجد شيء لتخطيه.", ephemeral=True)

    @discord.ui.button(label="⏹️ إيقاف شامل", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        if guild_id in queues:
            queues[guild_id].clear()
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await interaction.followup.send("⏹️ تم إيقاف التشغيل وتفريغ قائمة الانتظار.", ephemeral=True)
        else:
            await interaction.followup.send("❌ البوت غير متصل.", ephemeral=True)

# ----------------- 4. دالة التشغيل والتصميم الفخم -----------------
def play_next(guild_id, interaction_or_channel):
    if guild_id in queues and len(queues[guild_id]) > 0:
        song = queues[guild_id].pop(0)
        vc = song['vc']
        
        player = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)
        vc.play(player, after=lambda e: play_next(guild_id, interaction_or_channel))
        
        embed = discord.Embed(
            title="🎧 جاري التشغيل الآن",
            description=f"**[{song['title']}]({song['link']})**",
            color=discord.Color.from_rgb(88, 101, 242)
        )
        
        embed.add_field(name="⏱️ المدة", value=f"`{song['duration']}`", inline=True)
        embed.add_field(name="👤 بواسطة", value=song['requester'].mention, inline=True)
        
        if song.get('thumbnail'):
            embed.set_image(url=song['thumbnail'])
            
        asyncio.run_coroutine_threadsafe(
            song['channel'].send(embed=embed, view=MusicControlView(song['channel'])),
            bot.loop
        )

# ----------------- 5. الأوامر والـ Slash Commands -----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'✅ البوت جاهز ويعمل باسم: {bot.user.name}')

@bot.tree.command(name="p", description="تشغيل أغنية بالبحث أو الرابط")
@app_commands.describe(query="اسم الأغنية أو الرابط")
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
    
    search_targets = []
    if query.startswith("http"):
        search_targets.append(query)
    else:
        search_targets.append(f"scsearch:{query}")
        search_targets.append(f"ytsearch:{query}")

    data = None
    last_error = None

    for target in search_targets:
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(target, download=False))
            if data and 'entries' in data and data['entries']:
                data = data['entries'][0]
            if data:
                break
        except Exception as e:
            last_error = e

    if not data:
        return await interaction.followup.send(f"❌ تعذر استخراج الصوت: {str(last_error)}")

    song_info = {
        'url': data['url'],
        'title': data.get('title', 'مقطع صوتي'),
        'link': data.get('webpage_url', query),
        'duration': format_duration(data.get('duration', 0)),
        'thumbnail': data.get('thumbnail'),
        'requester': interaction.user,
        'vc': vc,
        'channel': interaction.channel
    }

    if vc.is_playing() or vc.is_paused():
        queues[guild_id].append(song_info)
        embed = discord.Embed(
            title="📝 تم الإضافة إلى قائمة الانتظار",
            description=f"**[{song_info['title']}]({song_info['link']})**",
            color=discord.Color.blue()
        )
        embed.add_field(name="⏱️ المدة", value=f"`{song_info['duration']}`", inline=True)
        if song_info.get('thumbnail'):
            embed.set_thumbnail(url=song_info['thumbnail'])
        await interaction.followup.send(embed=embed)
    else:
        queues[guild_id].append(song_info)
        play_next(guild_id, interaction.channel)
        await interaction.followup.send("🎶 جاري إعداد وتكليف التشغيل...")

@bot.tree.command(name="s", description="تخطي الأغنية الحالية")
async def skip_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.followup.send("⏭️ تم تخطي المقطع.")
    else:
        await interaction.followup.send("❌ لا يوجد شيء لتخطيه حالياً.")

@bot.tree.command(name="stop", description="إيقاف التشغيل تماماً وتفريغ القائمة")
async def stop_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id = interaction.guild.id
    if guild_id in queues:
        queues[guild_id].clear()
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        await interaction.followup.send("⏹️ تم الإيقاف وتفريغ قائمة الانتظار.")
    else:
        await interaction.followup.send("❌ البوت ليس متصلاً بأي روم.")

# ----------------- 6. تشغيل الخادم والبوت -----------------
keep_alive()

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
