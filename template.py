import discord
from GoloBot import Transaction
from GoloBot.Auxilliaire import DataBase
from discord import Guild, TextChannel


class TemplateKOTSmith(discord.AutoShardedBot):
    guild: Guild = None
    teams: Transaction = None
    log_inscriptions: TextChannel = None
    logs: TextChannel = None
