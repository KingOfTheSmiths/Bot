#!/usr/bin/env python3
from discord import Guild, TextChannel
from discord.commands.context import ApplicationContext
from discord.ext import commands
from dotenv import dotenv_values

from template import TemplateKOTSmith
from wows import *

path = '/'.join(__file__.split('/')[:-1]) + '/'
config = DictPasPareil(casse=True, **dotenv_values(path + '.env'))


class KingOfTheSmiths(TemplateKOTSmith):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = self
        self.invite = 'https://discord.com/oauth2/authorize?client_id=1450214424249106534&permissions=8&integration_type=0&scope=bot+applications.commands'

        self.teams = DataBase(path + 'teams.json')
        self.open_register = '__inscriptions__ouvertes__'
        if self.open_register not in self.teams:
            self.teams[self.open_register] = False

        self.add_cog(Inscriptions(self))

        self.guild: Guild = None
        self.log_inscriptions: TextChannel = None

    async def on_ready(self):
        self.guild = await self.fetch_guild(1448770816631115790)
        self.log_inscriptions = await self.guild.fetch_channel(1450211194320453692)
        print(self.log_inscriptions)
        print(f'Connecté en tant que {self.user} (ID: {self.user.id})')
        print(self.invite)


class Inscriptions(commands.Cog):
    def __init__(self, bot: KingOfTheSmiths):
        self.bot = bot
        self.team_prefix = "Team "
        self.update_prefix("_")

    def update_prefix(self, new_prefix: str):
        to_del = []
        for team, data in self.bot.teams.items():
            if team.startswith(self.team_prefix):
                to_del.append(team)
                new_name = f"{new_prefix}{team[len(self.team_prefix):]}"
                self.bot.teams[new_name] = data
        for stuff in to_del:
            del self.bot.teams[stuff]
        self.team_prefix = new_prefix

    @commands.slash_command(name="toggle_inscription",
                            description="(Dés)Active la possibilité de s'inscrire")
    @commands.has_permissions(administrator=True)
    async def toggle_recrutement(self, ctx: ApplicationContext):
        await ctx.defer(ephemeral=True)
        etat = self.bot.teams[self.bot.open_register]
        self.bot.teams[self.bot.open_register] = not etat
        access = {True: 'ouvertes', False: 'fermées'}
        await ctx.respond(f"Les inscriptions sont désormais {access[not etat]}.")

    @commands.slash_command(name="inscription", description="S'inscrire.")
    @discord.option("nom", description="Nom de l'équipe", required=True)
    @discord.option("joueur1", description="Pseudo, ID ou wows-numbers du joueur 1", required=True)
    @discord.option("joueur2", description="Pseudo, ID ou wows-numbers du joueur 2", required=True)
    @discord.option("joueur3", description="Pseudo, ID ou wows-numbers du joueur 3", required=True)
    @discord.option("joueur4", description="Pseudo, ID ou wows-numbers du joueur 4", required=True)
    @discord.option("joueur5", description="Pseudo, ID ou wows-numbers du joueur 5", required=True)
    @discord.option("discord1", description="Discord du joueur 1", required=True)
    @discord.option("discord2", description="Discord du joueur 2", required=False)
    @discord.option("discord3", description="Discord du joueur 3", required=False)
    @discord.option("discord4", description="Discord du joueur 4", required=False)
    @discord.option("discord5", description="Discord du joueur 5", required=False)
    async def inscription(self, ctx: ApplicationContext, nom: str,
                          joueur1: str, joueur2: str, joueur3: str, joueur4: str, joueur5: str,
                          discord1: discord.Member, discord2: discord.Member = None, discord3: discord.Member = None,
                          discord4: discord.Member = None, discord5: discord.Member = None):
        await ctx.defer(ephemeral=True)
        if not self.bot.teams[self.bot.open_register]:
            await ctx.respond("Les inscriptions sont actuellement fermées.")
            return
        if not isinstance(nom, str) or not nom.startswith(self.team_prefix):
            nom = f"{self.team_prefix}{nom}"
        joueurs = [joueur1, joueur2, joueur3, joueur4, joueur5]
        discords = [discord1, discord2, discord3, discord4, discord5]
        players = {}
        async with ClientSession() as session:
            for i, joueur in enumerate(joueurs):
                if 'wows-numbers' in joueur:
                    if not joueur.startswith('https://'):
                        joueur = f"https://{joueur}"
                    player = await Player.from_wows_numbers(config.WARGAMING_API, joueur, session)
                else:
                    player = await Player(config.WARGAMING_API, joueur).load(session)
                players[player.id] = {
                    'name': player.name,
                    'discord': None if not hasattr(discords[i], 'id') else discords[i].id
                }
        if len(players) < 5:
            await ctx.respond("Il faut au moins 5 joueurs différents pour s'inscrire.\n"
                              "Les joueurs comptabilisés sont : "
                              + ', '.join(info['name'] for info in players.values()))
            return
        self.bot.teams[nom] = players
        embed = await ctx.invoke(self.list_team, nom=nom)
        if isinstance(embed, discord.Embed):
            await self.bot.log_inscriptions.send("Nouvelle équipe inscrite", embed=embed)

    @commands.slash_command(name="list_team", description="Liste les membres d'une équipe.")
    @discord.option("nom", description="Nom de l'équipe", required=True)
    async def list_team(self, ctx: ApplicationContext, nom: str):
        try:
            await ctx.defer(ephemeral=True)
        except:
            pass
        if not isinstance(nom, str) or not nom.startswith(self.team_prefix):
            nom = f"{self.team_prefix}{nom}"
        if nom not in self.bot.teams:
            await ctx.respond(f"L'équipe **{nom}** n'existe pas.")
            print(', '.join([f"{k} {type(k)}" for k in self.bot.teams.keys()]))
            return None
        team_data = self.bot.teams[nom]
        embed = GBEmbed(title=f"Membres de l'équipe {nom[len(self.team_prefix):]}")
        joueurs = ''
        for player_id, info in team_data.items():
            joueurs += f"- {info['name']}"
            if info['discord']:
                joueurs += f" - <@{info['discord']}>"
            joueurs += "\n"
        embed.add_field(name="Joueurs", value=joueurs)
        await ctx.respond(embed=embed)
        return embed

    @commands.slash_command(name="list_teams", description="Liste les équipes inscrites.")
    async def list_teams(self, ctx: ApplicationContext):
        await ctx.defer(ephemeral=True)
        teams = [team for team in self.bot.teams if team != self.bot.open_register]
        if not teams:
            await ctx.respond("Aucune équipe n'est inscrite.")
            return
        embed = GBEmbed(title="Équipes inscrites",
                        description="Vous pouvez voir la liste des joueurs d'une équipe avec </list_team:1454840321291849836>")
        embed.add_field(name="Équipes", value='\n'.join(f"- {team[len(self.team_prefix):]}" for team in teams))
        await ctx.respond(embed=embed)


if __name__ == "__main__":
    bot = KingOfTheSmiths(intents=discord.Intents.all())
    bot.run(config.DISCORD_TOKEN)
