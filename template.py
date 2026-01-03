import discord
from discord import Guild, TextChannel
from GoloBot.Auxilliaire import DataBase


class TemplateKOTSmith(discord.AutoShardedBot):
    guild: Guild = None
    teams: DataBase = None
    log_inscriptions: TextChannel = None
    logs: TextChannel = None
