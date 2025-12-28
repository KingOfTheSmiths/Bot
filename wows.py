from enum import Enum

from aiohttp import ClientSession
from GoloBot.Auxilliaire import *

# chemin
path = '/'.join(__file__.split('/')[:-1]) + '/'

discord_id_to_ingame = {}


class Ressource(Enum):
    coal = 'Charbon'
    steel = 'Acier'
    token = 'Certificat'
    RP = 'Point de Recherche'


# event Noël 2024
snowflakes_rewards = {5: (700, Ressource.coal),
                      6: (750, Ressource.coal),
                      7: (800, Ressource.coal),
                      8: (70, Ressource.steel),
                      9: (80, Ressource.steel),
                      10: (1, Ressource.token),
                      11: (200, Ressource.steel)}


def PR(actualDmg, expectedDmg, actualWins, expectedWins, actualFrags, expectedFrags):
    # Step 1 - Ratios
    rDmg = actualDmg / expectedDmg
    rWins = actualWins / expectedWins
    rFrags = actualFrags / expectedFrags
    # Step 2 - Normalize
    nDmg = max(0, (rDmg - 0.4) / (1 - 0.4))
    nWins = max(0, (rWins - 0.7) / (1 - 0.7))
    nFrags = max(0, (rFrags - 0.1) / (1 - 0.1))
    # Step 3 - PR value
    return 700 * nDmg + 300 * nWins + 150 * nFrags


class Player:
    def __init__(self, token, name_or_id, *, realm='eu'):
        self.token: str = token
        self.name_or_id = name_or_id
        self.realm: str = realm
        self.loaded: bool = False

        # nécessite load()
        self.id: int = None
        self.personal_data: dict = None
        self.name: str = None
        self.wows_numbers: str = 'https://wows-numbers.com'
        self.stats: dict = None
        self.clan_data: dict = None
        self.clan: Clan = Clan(self.token, None, realm=self.realm)

    async def load(self, session: ClientSession):
        self.loaded = False
        self.id = await self.get_id(self.token, self.name_or_id, session, self.realm)
        self.personal_data = await self.get_player_personal_data(self.token, self.id, session, self.realm)
        self.name: str = self.personal_data['nickname']
        self.wows_numbers: str = f"https://wows-numbers.com/player/{self.id},{self.name}/"
        self.clan_data: dict = await self.get_player_clan_data(self.token, self.id, session, self.realm)
        if self.clan_data is not None:
            self.clan: Clan = await Clan(self.token, self.clan_data['clan_id'], realm=self.realm).load(session)
        self.loaded = True
        return self

    def __str__(self):
        if self.clan:
            return f"[[{self.clan.tag}] {self.name}]({self.wows_numbers})"
        else:
            return f"[{self.name}]({self.wows_numbers})"

    def __eq__(self, other):
        if isinstance(other, Player):
            return self.id == other.id
        return False

    def __gt__(self, other):
        if isinstance(other, self.__class__):
            if self.clan == other.clan:
                srole = self.clan_data['role']
                orole = other.clan_data['role']
                return Clan.roles_strength[srole] > Clan.roles_strength[orole]
        return False

    def __lt__(self, other):
        if isinstance(other, self.__class__):
            if self.clan == other.clan:
                srole = self.clan_data['role']
                orole = other.clan_data['role']
                return Clan.roles_strength[srole] < Clan.roles_strength[orole]
        return False

    def __call__(self, *args, **kwargs):
        # Requête que __aiter__ envoie pour récupérer la liste des navires du joueur
        if isinstance(kwargs.get('in_port'), bool):
            self._generator_request = (f"https://api.worldofwarships.eu/wows/ships/stats/"
                                       f"?application_id={self.token}"
                                       f"&account_id={self.id}"
                                       f"&in_garage={int(kwargs['in_port'])}")
        return self

    # Itère sur les bateaux du joueur
    async def __aiter__(self):
        async with ClientSession() as session:
            if not hasattr(self, '_generator_request') or not self._generator_request:
                self.__call__(in_port=True)
            async with session.get(self._generator_request) as response:
                json = await response.json()
                for ship in json['data'][str(self.id)]:
                    yield await Ship(self.token, ship['ship_id']).load(session)

    @classmethod
    async def get_id(cls, token, name_or_id, session: ClientSession, realm='eu') -> int:
        if not name_or_id:
            return None

        if isinstance(name_or_id, int) or name_or_id.isdigit():
            idp = int(name_or_id)

        elif isinstance(name_or_id, str):
            request = (f"https://api.worldofwarships.{realm}/wows/account/list/"
                       f"?application_id={token}"
                       f"&search={name_or_id}")
            async with session.get(request) as response:
                json = await response.json()
                idp = json["data"][0]["account_id"]

        else:
            raise Exception(f"{name_or_id} invalide sur le serveur {realm}")
        return idp

    @classmethod
    async def get_player_personal_data(cls, token, account_id, session: ClientSession, realm='eu') -> dict:
        if account_id is None:
            return None

        request = (f"https://api.worldofwarships.{realm}/wows/account/info/"
                   f"?application_id={token}"
                   f"&account_id={account_id}")
        async with session.get(request) as response:
            json = await response.json()
        return json['data'][str(account_id)]

    @classmethod
    async def get_player_clan_data(cls, token, account_id, session: ClientSession, realm='eu') -> dict:
        if account_id is None:
            return None

        request = (f"https://api.worldofwarships.{realm}/wows/clans/accountinfo/"
                   f"?application_id={token}"
                   f"&account_id={account_id}")
        async with session.get(request) as response:
            json = await response.json()
        return json['data'][str(account_id)]

    @classmethod
    async def from_wows_numbers(cls, token, url, session: ClientSession, realm='eu'):
        # url format https://wows-numbers.com/player/account_id,account_name
        url_ = url.lower().strip('/').split('/')
        if 'player' not in url_:
            return None
        account = url_[-1]
        account_id = int(account.split(',')[0])
        return await cls(token=token, name_or_id=account_id, realm=realm).load(session)

    async def set_stats(self, token, session: ClientSession):
        if not self.loaded:
            await self.load(session)
        kwargs = {'actualDmg': 0, 'expectedDmg': 0,
                  'actualWins': 0, 'expectedWins': 0,
                  'actualFrags': 0, 'expectedFrags': 0}
        url = 'https://api.wows-numbers.com/personal/rating/expected/json/'
        async with session.get(url) as response:
            expected = await response.json()
        async for ship in self:
            raw, nb_games = await self.raw_stats(ship, session)
            for key, value in raw.items():
                kwargs[key] += value
            kwargs['expectedDmg'] += expected[ship.id]['damage']
            kwargs['expectedWins'] += expected[ship.id]['wins'] * nb_games
            kwargs['expectedFrags'] += expected[ship.id]['frags']
            self.stats[ship.id] = {'PR': PR(**kwargs),
                                   'WR': 100 * raw['actualWins'] / nb_games}
        self.stats['global'] = {'PR': PR(**kwargs),
                                'WR': 100 * kwargs['actualWins'] / self.personal_data['statistics']['pvp']['battles']}

    async def raw_stats(self, ship, session: ClientSession):
        url = (f"https://api.worldofwarships.eu/wows/ships/stats/"
               f"?application_id={self.token}"
               f"&account_id={self.id}"
               f"&ship_id={ship.id}")
        async with session.get(url) as response:
            json = await response.json()
        kwargs = {'actualDmg': json['data'][str(self.id)][0]['pvp']['damage_dealt'],
                  'actualWins': json['data'][str(self.id)][0]['pvp']['wins'],
                  'actualFrags': json['data'][str(self.id)][0]['pvp']['frags']}
        nb_games = json['data'][str(self.id)][0]['pvp']['battles']
        return kwargs, nb_games

    # Raccourci prérempli
    async def update_user(self, user, session: ClientSession, force=False):
        if not self.loaded:
            await self.load(session)
        return await update_user(user, self, self.token, session, realm=self.realm, force=force)


# Crée un nouvel utilisateur
async def update_user(user, player, token, session: ClientSession, *, realm='eu', force=False):
    # Prétraitement du paramètre 'user'
    if hasattr(user, 'id'):
        user = user.id
    user = str(user)

    if not isinstance(player, Player):
        player = await Player(token, player, realm=realm).load(session)
    if user not in discord_id_to_ingame:
        if player is not None and realm is not None:
            discord_id_to_ingame[user] = player.id
    else:
        try:
            ig_id = discord_id_to_ingame[user]
            await Player(token, ig_id, realm=realm).load(session)  # on vérifie que le compte existe
            if force:
                discord_id_to_ingame[user] = player.id
        except:
            del discord_id_to_ingame[user]
            discord_id_to_ingame[user] = player.id
    discord_id_to_ingame.write()
    return discord_id_to_ingame.get(user)


class Clan:
    roles_enfr = {"commander": "Commandant",
                  "executive_officer": "Commandant en Second",
                  "recruitment_officer": "Recruteur",
                  "commissioned_officer": "Officier Commissionné",
                  "officer": "Officier Supérieur",
                  "private": "Aspirant"}
    role_fren = {v: k for k, v in roles_enfr.items()}
    roles_strength = {"commander": 5,
                      "executive_officer": 4,
                      "recruitment_officer": 3,
                      "commissioned_officer": 2,
                      "officer": 1,
                      "private": 0}

    def __init__(self, token, tag_or_id, *, realm='eu'):
        self.token: str = token
        self.tag_or_id = tag_or_id
        self.realm: str = realm
        self.loaded: bool = False

        # Nécessite load()
        self.id: int = None
        self.details: dict = None
        self.name: str = ''
        self.tag: str = ''
        self.members: list = list()
        self.wows_numbers: str = 'https://wows-numbers.com'

    async def load(self, session: ClientSession):
        self.loaded = False
        self.id = await self.get_id(self.token, self.tag_or_id, session, self.realm)
        self.details = await self.get_clan_details(self.token, self.id, session, self.realm)
        self.wows_numbers: str = "https://wows_numbers.com/clan/"
        if self.details is not None:
            self.name = self.details['name']
            self.tag = self.details['tag']
            self.members = self.details['members_ids']
            self.wows_numbers = f"https://wows-numbers.com/clan/{self.id},{self.tag}-{self.name.replace(' ', '-')}/"
        self.loaded = True
        return self

    def __str__(self):
        if self:
            return f"[[{self.tag}] {self.name}]({self.wows_numbers})"
        return "Aucun Clan"

    def __eq__(self, other):
        if isinstance(other, Clan):
            return self.id == other.id
        return False

    def __contains__(self, item):
        if isinstance(item, Player):
            item = item.id
        if isinstance(item, int):
            return item in self.members
        return False

    def __len__(self):
        return self.details['members_count']

    def __getitem__(self, item):
        player = self.members[item]
        if not isinstance(player, Player):
            player = Player(self.token, player, realm=self.realm)
        return player

    # Itère sur les joueurs présents dans le clan
    async def __aiter__(self):
        async with ClientSession() as session:
            for player in self.members:
                if not isinstance(player, Player):
                    player = await Player(self.token, player, realm=self.realm).load(session)
                yield player

    def __bool__(self):
        return self.id is not None

    @classmethod
    async def get_id(cls, token, tag_or_id, session: ClientSession, realm='eu') -> int:
        if tag_or_id is None:
            return None

        if isinstance(tag_or_id, int):
            idc = tag_or_id

        elif isinstance(tag_or_id, str):
            request = (f"https://api.worldofwarships.{realm}/wows/clans/list/"
                       f"?application_id={token}"
                       f"&search={tag_or_id}")
            async with session.get(request) as response:
                json = await response.json()
            idc = json['data'][0]['clan_id']

        else:
            raise Exception(f"[{tag_or_id}] invalide sur le serveur {realm}")
        return idc

    @classmethod
    async def get_clan_details(cls, token, clan_id, session: ClientSession, realm='eu') -> dict:
        if clan_id is None:
            return None

        request = (f"https://api.worldofwarships.{realm}/wows/clans/info/"
                   f"?application_id={token}"
                   f"&clan_id={clan_id}")
        async with session.get(request) as response:
            json = await response.json()
        return json['data'][str(clan_id)]

    @classmethod
    async def from_wows_numbers(cls, token, url, session: ClientSession, realm='eu'):
        url_ = url.lower().strip('/').split('/')
        if 'clan' not in url_:
            raise Exception(f"{url} ne correspond pas aux stats d'un clan")
        clan = url_[-1]
        clan_id = clan.split(',')[0]
        return await cls(token, clan_id, realm=realm).load(session)


class Ship:
    tiers = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', '*']

    def __init__(self, token, name_or_id):
        self.token: str = token
        self.name_or_id = name_or_id
        self.loaded: bool = False

        # Nécessite load()
        self.id: int = None
        self.data: dict = None
        self.description: str = ''
        self.name: str = ''
        self.tier: int = None
        self.is_premium: bool = None
        self.is_special: bool = None
        self.is_techtree: bool = None
        self.type: str = ''
        self.nation: str = ''
        self.parameters: dict = None

    async def load(self, session: ClientSession):
        self.loaded = False
        self.id: int = await self.get_id(self.token, self.name_or_id, session)

        self.data: dict = await self.get_data(self.token, self.id, session)
        autoset = ['description', 'name', 'tier', 'is_premium', 'is_special', 'type', 'nation']
        for key in autoset:
            setattr(self, key, None)
            if self.data is not None and key in self.data:
                value = self.data[key]
                if key == 'nation':
                    value = value.replace('_', ' ')
                setattr(self, key, value)
        self.is_techtree = not self.is_premium and not self.is_special
        self.parameters = await self.get_parameters(self.token, self.id, session)
        self.loaded = True
        return self

    def __str__(self):
        if self:
            nation = self.nation.upper()
            if len(self.nation) > 4:
                nation = self.nation.title()
            tier = self.tiers[self.tier - 1]
            return f'{nation} {tier} {self.name}'
        return 'Navire Inconnu'

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        return False

    def __bool__(self):
        return None not in self.__dict__.values()

    @classmethod
    async def get_all(cls, token, session: ClientSession):
        fini = False
        page_no = 1
        while not fini:
            req = (f'https://api.worldofwarships.eu/wows/encyclopedia/ships/'
                   f'?application_id={token}'
                   f'&page_no={page_no}')
            async with session.get(req) as response:
                json = await response.json()
                page_no += 1
                fini = json['status'] == 'error'
                if not fini:
                    for data in json['data'].items():
                        yield data

    @classmethod
    async def get_id(cls, token, name_or_id, session: ClientSession, exact=True) -> int:
        if not name_or_id:
            return None

        if isinstance(name_or_id, int) or name_or_id.isdigit():
            return int(name_or_id)

        def func(txt):
            if exact:
                return name_or_id.lower() == strip_accents(txt).lower()
            else:
                return name_or_id.lower() in strip_accents(txt).lower()

        async for ship_id, value in cls.get_all(token, session):
            if func(value['name']):
                return int(ship_id)

        # On n'a pas trouvé une correspondance exacte
        if exact:
            return await cls.get_id(token=token, name_or_id=name_or_id, session=session, exact=False)

    @classmethod
    async def get_data(cls, token, ship_id, session: ClientSession) -> dict:
        req = (f'https://api.worldofwarships.eu/wows/encyclopedia/ships/'
               f'?application_id={token}'
               f'&ship_id={ship_id}'
               f'&language=fr')
        async with session.get(req) as response:
            json = await response.json()
        return json['data'][str(ship_id)]

    @classmethod
    async def get_parameters(cls, token, ship_id, session: ClientSession) -> dict:
        req = (f'https://api.worldofwarships.eu/wows/encyclopedia/shipprofile/'
               f'?application_id={token}'
               f'&ship_id={ship_id}'
               f'&language=fr')
        async with session.get(req) as response:
            json = await response.json()
        return json['data'][str(ship_id)]

    @classmethod
    async def get_modules(cls, token, module_id, session: ClientSession) -> dict:
        req = (f'https://api.worldofwarships.eu/wows/encyclopedia/modules/'
               f'?application_id={token}'
               f'&module_id={module_id}'
               f'&language=fr')
        async with session.get(req) as response:
            json = await response.json()
        return json['data'][str(module_id)]

    def format_parameters(self) -> dict:
        params = dict()
        data = self.parameters['mobility']
        params['Manianilité'] = {'Temps de Basculement': f"{data['rudder_time']} s",
                                 'Vitesse Maximale': f"{data['max_speed']} kts",
                                 'Rayon de Giration': f"{data['turning_radius']} m"}
        data = self.parameters['artillery']
        params['Batterie Principale'] = {'Dispersion Maximale': f"{data['max_dispersion']} m",
                                         'AP': f"{data}"}
        return params

    def embed_stats(self) -> GBEmbed:
        embed = GBEmbed(title=str(self), color=0xffffff * self.tier // 11, description=self.description)
        embed.set_image(url=self.data['images']['large'])
        # Survivabilité
        data = self.parameters['armour']
        text = f"""Points de Vie <yellow>{data['health']}<reset>
Protection AntiTorpille <yellow>{data['flood_damage']}<reset> %"""
        embed.add_field(name='Survivabilité', value=ANSI.converter(text))

        # Maniabilité
        data = self.parameters['mobility']
        text = f"""Temps de Basculement <yellow>{data['rudder_time']}<reset> s
Vitesse Maximale <yellow>{data['max_speed']}<reset> kts
Rayon de Giration <yellow>{data['turning_radius']}<reset> m
"""
        # Maniabilté sous l'eau
        data = self.parameters['submarine_mobility']
        if data:
            text += f"""<cyan>Immergé<reset>
    Vitesse <yellow>{data['max_speed_under_water']}<reset> kts
    Temps de Basculement <yellow>{data['buoyancy_rudder_time']}<reset> s
    Vitesse Verticale <yellow>{data['max_buoyancy_speed']}<reset> m/s"""
        embed.add_field(name='Maniabilité', value=ANSI.converter(text))

        # Batterie Principale
        data = self.parameters['artillery']
        if data is not None:
            text = f"""Portée <yellow>{data['distance']}<reset> km
Dispersion Maximale <yellow>{data['max_dispersion']}<reset> m
Temps de Rotation à 180° <yellow>{data['rotation_time']}<reset> s
Temps de Rechargement <yellow>{data['shot_delay']}<reset> s
"""
            for slot in data['slots'].values():
                text += f"""<yellow>{slot['guns']}<reset>×<yellow>{slot['barrels']} <cyan>{slot['name']}
"""
            for name, value in data['shells'].items():
                text += f"""<cyan>{name}<reset>
    Alpha <yellow>{value['damage']}<reset>
    Vitesse <yellow>{value['bullet_speed']}<reset> m/s
"""
                fire_chance = value['burn_probability']
                if fire_chance:
                    text += f"""    Chance d'Incendie <yellow>{fire_chance}<reset> %"""
            embed.add_field(name='Batterie Principale', value=ANSI.converter(text))

        # Batterie Secondaire
        data = self.parameters['atbas']
        if data:
            text = f"""Portée <yellow>{data['distance']}<reset> km
"""
            if 'slots' in data:
                for slot in data['slots'].values():
                    text += f"""<cyan>{slot['name']}<reset>
    Temps de Rechargement <yellow>{slot['shot_delay']}<reset> s
    Alpha <yellow>{slot['damage']}<reset>
    Chance d'Incendie <yellow>{slot['burn_probability']}<reset> %
"""
            embed.add_field(name='Batterie Secondaire', value=ANSI.converter(text))

        # Dissimulation
        data = self.parameters['concealment']
        text = f"""Navires <yellow>{data['detect_distance_by_ship']}<reset> km
Avions <yellow>{data['detect_distance_by_plane']}<reset> km
Sous Marins <yellow>{data['detect_distance_by_submarine']}<reset> km"""
        embed.add_field(name='Dissimulation', value=ANSI.converter(text))

        # ASW
        data = self.parameters['depth_charge']
        if data:
            text = f"""Nombre <yellow>{data['max_packs']}<reset>×<yellow>{data['num_bombs_in_pack']}<reset>
Dégâts <yellow>{data['bomb_max_damage']}<reset>
Temps de Rechargement <yellow>{data['reload_time']}"""
            embed.add_field(name='Grenades', value=ANSI.converter(text))

        # Batterie (subs)
        data = self.parameters['submarine_battery']
        if data:
            text = f"""Capacité <yellow>{data['max_capacity']}<reset>
Consommation <yellow>{data['consumption_rate']}<reset> /s
Régénération <yellow>{data['regen_rate']}<reset> /s"""
            embed.add_field(name='Batterie', value=ANSI.converter(text))

        # Sonar
        if 'sonar' in self.parameters:
            data = self.parameters['sonar']
            text = f"""Portée <yellow>{data['wave_max_dist']}<reset> km
Temps de Rechargement <yellow>{data['wave_shot_delay']}<reset> s
Vélocité <yellow>{data['wave_speed_max']}<reset> m/s
Largeur <yellow>{data['wave_width']}<reset> m
Durée Simple <yellow>{data['wave_duration_0']}<reset> s
Durée Double <yellow>{data['wave_duration_1']}<reset> s"""
            embed.add_field(name='Sonar', value=ANSI.converter(text))

        # Torpilles
        data = self.parameters['torpedoes']
        if data:
            text = f"""Portée <yellow>{data['distance']}<reset> km
Dégâts <yellow>{data['max_damage']}<reset>
Temps de Rechargement <yellow>{data['reload_time']}<reset> s
Temps de Rotation à 180° <yellow>{data['rotation_time']}<reset> s
Vitesse <yellow>{data['torpedo_speed']}<reset> kts
Détectabilité <yellow>{data['visibility_dist']}<reset> km
"""
            for slot in data['slots'].values():
                text += f"""<yellow>{slot['guns']}<reset>×<yellow>{slot['barrels']} <cyan>{slot['name']}<reset>"""
            embed.add_field(name='Torpilles', value=ANSI.converter(text))

        return embed
