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

# دالة تحويل الثواني إلى صيغة وقت أنيقة (MM:SS أو HH:MM:SS)
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

# ----------------- 4. دالة التشغيل بطباعة تصميم الـ Embed الفخم -----------------
def play_next(guild_id, interaction_or_channel):
    if guild_id in queues and len(queues[guild_id]) > 0:
        song = queues[guild_id].pop(0)
        vc = song['vc']
        
        player = discord.FFmpegPCMAudio(song['url'], **FFMPEG_OPTIONS)
        vc.play(player, after=lambda e: play_next(guild_id, interaction_or_channel))
        
        # تصميم الـ Embed العصري الجديد
        embed = discord.Embed(
            title="🎧 جاري التشغيل الآن",
            description=f"**[{song['title']}]({song['link']})**",
            color=discord.Color.from_rgb(88, 101, 242) # لون أزرق فخم
        )
        
        embed.add_field(name="⏱️ المدة", value=f"`{song['duration']}`", inline=True)
        embed.add_field(name="👤 بواسطة", value=song['requester'].mention, inline=True)
        
        if song.get('thumbnail'):
            embed.set_image(url=song['thumbnail']) # إظهار غلاف المقطع بحجم كبير وفخم
            
        embed.set_footer(
            text="Muhammad Abdu Bot • استمتع بالاستماع!", 
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        
        async
