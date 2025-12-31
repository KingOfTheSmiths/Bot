#!/usr/bin/env python3
from io import BytesIO  # récupération de PP + bannière

from discord import Guild, TextChannel
from discord.commands.context import ApplicationContext
from discord.ext import commands
from GoloBot.UI import *

from template import TemplateKOTSmith
from wows import *

path = '/'.join(__file__.split('/')[:-1]) + '/'
config = DictPasPareil(casse=True, **dotenv_values(path + '.env'))

TEAM_PREFIX = '.'


def update_prefix(new_prefix: str):
    global TEAM_PREFIX
    to_del = []
    for team, data in Database('teams.json').items():
        if team.startswith(TEAM_PREFIX):
            to_del.append(team)
            new_name = f"{new_prefix}{team[len(TEAM_PREFIX):]}"
            self.bot.teams[new_name] = data
    for stuff in to_del:
        del self.bot.teams[stuff]
    TEAM_PREFIX = new_prefix


def format_with_prefix(name) -> str:
    if not isinstance(name, str) or not name.startswith(TEAM_PREFIX):
        name = f"{TEAM_PREFIX}{name}"
    return name


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
        self.add_cog(General(self))

        self.guild: Guild = None
        self.log_inscriptions: TextChannel = None

    async def on_ready(self):
        self.guild = await self.fetch_guild(1448770816631115790)
        self.log_inscriptions = await self.guild.fetch_channel(1450211194320453692)

        # Nom, PP et Bannière
        kwargs = {'username': self.guild.name}
        async with ClientSession() as session:
            async with session.get(self.guild.icon.url) as resp:
                img = await resp.read()
                with BytesIO(img) as file:
                    kwargs['avatar'] = file.getvalue()
            # async with session.get(self.guild.banner.url) as resp:
            #     img = await resp.read()
            #     with BytesIO(img) as file:
            #         kwargs['banner'] = file.getvalue()
        await self.user.edit(**kwargs)

        # Message de statut du bot
        activity = discord.Activity(name=self.guild.name,
                                    type=discord.ActivityType.watching)
        await self.change_presence(activity=activity)

        print(f'Connecté en tant que {self.user} (ID: {self.user.id})')
        print(self.invite)


class General(commands.Cog):
    def __init__(self, bot: KingOfTheSmiths):
        self.bot = bot

    @commands.slash_command(name="restart", description="Redémarre le bot.")
    @commands.has_permissions(administrator=True)
    async def restart(self, ctx: ApplicationContext):
        await ctx.respond(f"Redémarrage du bot dans 5s", ephemeral=True)
        await self.bot.close()


class Inscriptions(commands.Cog):
    def __init__(self, bot: KingOfTheSmiths):
        self.bot = bot

    @commands.slash_command(name="toggle_inscription",
                            description="(Dés)Active la possibilité de s'inscrire")
    @commands.has_permissions(administrator=True)
    async def toggle_recrutement(self, ctx: ApplicationContext):
        await ctx.defer(ephemeral=True)
        etat = self.bot.teams[self.bot.open_register]
        self.bot.teams[self.bot.open_register] = not etat
        access = {True: 'ouvertes', False: 'fermées'}
        await ctx.respond(f"Les inscriptions sont désormais {access[not etat]}.")

    @commands.slash_command(name="inscription",
                            description="S'inscrire. Il faut renseigner 5 joueurs et au moins 1 compte discord.")
    @discord.option("nom", description="Nom de l'équipe", required=True)
    @discord.option("joueur1", description="Pseudo, ID ou wows-numbers du joueur 1", required=True)
    @discord.option("joueur2", description="Pseudo, ID ou wows-numbers du joueur 2", required=True)
    @discord.option("joueur3", description="Pseudo, ID ou wows-numbers du joueur 3", required=True)
    @discord.option("joueur4", description="Pseudo, ID ou wows-numbers du joueur 4", required=True)
    @discord.option("joueur5", description="Pseudo, ID ou wows-numbers du joueur 5", required=True)
    @discord.option("discord2", description="Discord du joueur 2", required=False)
    @discord.option("discord3", description="Discord du joueur 3", required=False)
    @discord.option("discord4", description="Discord du joueur 4", required=False)
    @discord.option("discord5", description="Discord du joueur 5", required=False)
    async def inscription(self, ctx: ApplicationContext, nom: str,
                          joueur1: str, joueur2: str, joueur3: str, joueur4: str, joueur5: str,
                          discord2: discord.Member = None, discord3: discord.Member = None,
                          discord4: discord.Member = None, discord5: discord.Member = None):
        await ctx.defer(ephemeral=True)
        if not self.bot.teams[self.bot.open_register]:
            await ctx.respond("Les inscriptions sont actuellement fermées.")
            return
        nom = format_with_prefix(nom)
        if nom in self.bot.teams:
            await ctx.respond(f"L'équipe **{nom}** est déjà inscrite.")
            return
        joueurs = [joueur1, joueur2, joueur3, joueur4, joueur5]
        discords = [ctx.user, discord2, discord3, discord4, discord5]
        players = {}
        async with ClientSession() as session:
            for i, joueur in enumerate(joueurs):
                if joueur.startswith('wows-numbers.com'):
                    joueur = f"https://{joueur}"
                if joueur.startswith('https://wows-numbers.com'):
                    player = await Player.from_wows_numbers(config.WARGAMING_API, joueur, session)
                else:
                    player = await Player(config.WARGAMING_API, joueur).load(session)
                players[player.id] = {
                    'name': player.name,
                    'discord': None if not hasattr(discords[i], 'id') else discords[i].id,
                    'leader': i == 0
                }
        if len(players) < 5:
            await ctx.respond("Il faut au moins 5 joueurs différents pour s'inscrire.\n"
                              "Les joueurs comptabilisés sont : "
                              + ', '.join(info['name'] for info in players.values()))
            return
        self.bot.teams[nom] = {'validee': False, 'members': players}
        embed = await ctx.invoke(self.list_team, nom=nom)
        if isinstance(embed, discord.Embed):
            await self.bot.log_inscriptions.send("Nouvelle équipe inscrite",
                                                 embed=embed,
                                                 view=InscriptionView(self.bot, nom))

    @commands.slash_command(name="list_team", description="Liste les membres d'une équipe.")
    @discord.option("nom", description="Nom de l'équipe", required=True)
    async def list_team(self, ctx: ApplicationContext, nom: str):
        try:
            await ctx.defer(ephemeral=True)
        except:
            pass
        nom = format_with_prefix(nom)
        if nom not in self.bot.teams:
            await ctx.respond(f"L'équipe **{nom}** n'existe pas.")
            print(', '.join([f"{k} {type(k)}" for k in self.bot.teams.keys()]))
            return None
        team_data = self.bot.teams[nom]
        embed = GBEmbed(title=f"Membres de l'équipe {nom[len(TEAM_PREFIX):]}")
        embed.description = f"Candidature validée : {'oui' if team_data['validee'] else 'non'}"
        joueurs = ''
        for player_id, info in team_data['members'].items():
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
        embed.add_field(name="Équipes", value='\n'.join(f"- {team[len(TEAM_PREFIX):]}" for team in teams))
        await ctx.respond(embed=embed)


class BoutonAcceptInscription(GButton):
    def __init__(self, bot: KingOfTheSmiths, team_name: str, *args, **kwargs):
        super().__init__(bot, *args, **kwargs)
        self.name = team_name

    async def callback(self, interaction: Interaction):
        if not interaction.guild.id == 1448770816631115790:
            return
        team = self.bot.teams[self.name]
        if team['validee']:
            await interaction.response.send_message("Cette candidature a déjà été acceptée", ephemeral=True)
            return
        team['validee'] = True
        await interaction.response.send_message("Candidature acceptée", ephemeral=True)
        embed = interaction.message.embeds[0]
        embed.description = f"Acceptée par {interaction.user.mention}"
        embed.colour = discord.Color.green()
        await interaction.message.edit(content=None, embed=embed, view=None)
        representant = await self.bot.guild.fetch_role(1450213010798022768)
        participant = await self.bot.guild.fetch_role(1448776038896111647)
        members = [m for m in team['members'].values()]
        for db_member in members:
            if db_member['discord'] is None:
                continue
            try:
                member: discord.Member = await self.bot.guild.fetch_member(db_member['discord'])
                await member.add_roles(participant)
                if db_member['leader']:
                    await member.add_roles(representant)
                    message = f"Votre équipe **{self.name[len(TEAM_PREFIX):]}** a été acceptée pour le **{self.bot.user.name}**"
                    await member.send(message)
            except Exception as e:
                print(e)


class BoutonRefusInscription(GButton):
    def __init__(self, bot: KingOfTheSmiths, team_name: str, *args, **kwargs):
        super().__init__(bot, *args, **kwargs)
        self.name = team_name

    async def callback(self, interaction: Interaction):
        if not interaction.guild.id == 1448770816631115790:
            return
        team = self.bot.teams[self.name]
        if team['validee']:
            await interaction.response.send_message("Cette candidature a déjà été acceptée", ephemeral=True)
            return
        members = [m for m in team['members'].values() if m['leader']]
        del self.bot.teams[self.name]
        await interaction.response.send_message("Candidature refusée", ephemeral=True)
        embed = interaction.message.embeds[0]
        embed.description = f"Refusée par {interaction.user.mention}"
        embed.colour = discord.Color.red()
        await interaction.message.edit(content=None, embed=embed, view=None)
        for member in members:
            if member['leader']:
                try:
                    user = await self.bot.fetch_user(member['discord'])
                    message = f"Votre équipe **{self.name[len(TEAM_PREFIX):]}** n'a pas été acceptée pour le **{self.bot.user.name}**"
                    await user.send(message)
                except:
                    pass


class InscriptionView(GBView):
    def __init__(self, bot: TemplateKOTSmith, team_name: str, *args, **kwargs):
        kwargs['timeout'] = None
        super().__init__(bot, *args, **kwargs)
        self.add_item(BoutonAcceptInscription(bot, team_name, label="Accepter", style=discord.ButtonStyle.success))
        self.add_item(BoutonRefusInscription(bot, team_name, label="Refuser", style=discord.ButtonStyle.danger))


if __name__ == "__main__":
    bot = KingOfTheSmiths(intents=discord.Intents.all())
    bot.run(config.DISCORD_TOKEN)
