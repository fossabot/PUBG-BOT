import discord
import logging

from discord.state import ConnectionState
from typing import Optional, List, Union

from module.components import ActionRow, Button, Selection
from module.errors import InvalidArgument
from module.message import Message
from module.message import _files_to_form, _allowed_mentions
from module.http import HttpClient, InteractionData
from utils.prefix import get_prefix

log = logging.getLogger()


class InteractionContext:
    def __init__(self, payload: dict, client: discord.Client):
        self.client = client
        self.id: int = getattr(discord.utils, "_get_as_snowflake")(payload, "id")
        self.version = payload.get("version")
        self.type = payload.get("type")
        self.token = payload.get("token")
        self.application = getattr(discord.utils, "_get_as_snowflake")(payload, "application_id")

        self._state: ConnectionState = getattr(client, "_connection")

        self.guild_id = payload.get("guild_id")
        self.channel_id = payload.get("channel_id")
        if self.guild_id is not None:
            self.guild: Optional[discord.Guild] = self.client.get_guild(int(self.guild_id))
        else:
            self.guild: Optional[discord.Guild] = None
        self.channel = self._state.get_channel(int(self.channel_id))

        if self.guild is not None:
            member = payload.get("member")
            self.author = discord.Member(data=member, state=self._state, guild=self.guild)
        else:
            user = payload.get("user")
            self.author = discord.User(data=user, state=self._state)
        self.created_at = discord.utils.snowflake_time(self.id)

        self.deferred = False
        self.responded = False

        data = InteractionData(interaction_token=self.token, interaction_id=self.id, application_id=self.application)
        self.http = HttpClient(http=self.client.http, data=data)

    @property
    def prefix(self):
        return get_prefix(None, self)[0]

    @staticmethod
    def _get_payload(
            content=None,
            tts: bool = False,
            embed=None,
            hidden: bool = False,
            allowed_mentions=None,
            components=None
    ) -> dict:

        payload = {}
        if content:
            payload['content'] = content
        if tts:
            payload['tts'] = tts
        if embed:
            payload['embeds'] = embed
        if allowed_mentions:
            payload['allowed_mentions'] = allowed_mentions
        if hidden:
            payload['flags'] = 1 << 6
        if components:
            payload['components'] = components
        return payload

    async def defer(self, hidden: bool = False):
        base = {"type": 5}
        if hidden:
            base["data"] = {"flags": 64}

        await self.http.post_defer_response(payload=base)
        self.deferred = True
        return

    async def send(
            self,
            content=None,
            *,
            tts: bool = False,
            embed: discord.Embed = None,
            embeds: List[discord.Embed] = None,
            file: discord.File = None,
            files: List[discord.File] = None,
            hidden: bool = False,
            allowed_mentions: discord.AllowedMentions = None,
            components: List[Union[ActionRow, Button, Selection]] = None
    ):
        if file is not None and files is not None:
            raise InvalidArgument()
        if embed is not None and embeds is not None:
            raise InvalidArgument()

        content = str(content) if content is not None else None
        if embed is not None:
            embeds = [embed]
        if embeds is not None:
            embeds = [embed.to_dict() for embed in embeds]
        if file:
            files = [file]
        if components is not None:
            components = [i.to_all_dict() if isinstance(i, ActionRow) else i.to_dict() for i in components]

        allowed_mentions = _allowed_mentions(self._state, allowed_mentions)
        payload = self._get_payload(
            content=content,
            embed=embeds,
            tts=tts,
            hidden=hidden,
            allowed_mentions=allowed_mentions,
            components=components,
        )

        if files:
            form = _files_to_form(files=files, payload=payload)
        else:
            form = None

        if not self.responded:
            if files:
                await self.defer(hidden=hidden)

            if self.deferred:
                resp = await self.http.edit_initial_response(payload=payload, form=form, files=files)
            else:
                await self.http.post_initial_response(payload=payload)
                resp = await self.http.get_initial_response()
            self.responded = True
        else:
            resp = await self.http.post_followup(payload=payload, form=form, files=files)
        ret = Message(state=self._state, channel=self.channel, data=resp)

        if files:
            for i in files:
                i.close()
        return ret

    async def edit(
            self,
            message_id="@original",
            content=None,
            *,
            embed: discord.Embed = None,
            embeds: List[discord.Embed] = None,
            file: discord.File = None,
            files: List[discord.File] = None,
            allowed_mentions: discord.AllowedMentions = None,
            components: List[Union[ActionRow, Button, Selection]] = None
    ):
        if file is not None and files is not None:
            raise InvalidArgument()
        if embed is not None and embeds is not None:
            raise InvalidArgument()

        content = str(content) if content is not None else None
        if embed is not None:
            embeds = [embed]
        if embeds is not None:
            embeds = [embed.to_dict() for embed in embeds]
        if file:
            files = [file]
        if components is not None:
            components = [i.to_all_dict() if isinstance(i, ActionRow) else i.to_dict() for i in components]

        allowed_mentions = _allowed_mentions(self._state, allowed_mentions)

        payload = self._get_payload(
            content=content,
            embed=embeds,
            allowed_mentions=allowed_mentions,
            components=components,
        )

        if files:
            form = _files_to_form(files=files, payload=payload)
        else:
            form = None

        if message_id == "@original":
            resp = await self.http.edit_initial_response(payload=payload, form=form, files=files)
        else:
            resp = await self.http.edit_followup(message_id, payload=payload, form=form, files=files)
        ret = Message(state=self._state, channel=self.channel, data=resp)

        if files:
            for file in files:
                file.close()
        return ret

    async def delete(self, message_id="@original"):
        if message_id == "@original":
            await self.http.delete_initial_response()
        else:
            await self.http.delete_followup(message_id)
        return


class SlashContext(InteractionContext):
    def __init__(self, payload: dict, client: discord.Client):
        super().__init__(payload, client)
        self.type = payload.get("type", 2)
        data = payload.get("data", {})

        self.name = data.get("name")
        self.options = {}
        for option in data.get("options", []):
            key = option.get("name")
            value = option.get("value")
            option_type = option.get("type")
            if option_type == 3:
                self.options[key]: str = value
            elif option_type == 4:
                self.options[key]: int = value
            elif option_type == 5:
                self.options[key] = bool(value)
            elif option_type == 6:
                if self.guild is not None:
                    self.member = self.guild.get_member(value)
                else:
                    self.member = client.get_user(value)
            elif option_type == 7 and self.guild is not None:
                self.options[key] = self.guild.get_channel(value)
            elif option_type == 8:
                self.options[key]: discord.Role = self.guild.get_role(value)
            elif option_type == 10:
                self.options[key]: float = float(value)
            else:
                self.options[key] = value

    @property
    def content(self):
        options = [str(self.options[i]) for i in self.options.keys()]
        return f"/{self.name} {' '.join(options)}"


class ComponentsContext(InteractionContext):
    def __init__(self, payload: dict, client: discord.Client):
        super().__init__(payload, client)
        self.type = payload.get("type", 3)
        data = payload.get("data", {})

        self.custom_id = data.get("custom_id")
        self.component_type = data.get("component_type")
        if self.component_type == 3:
            self.values: List[str] = data.get("values")
        else:
            self.values: List[str] = []

        self.message = Message(state=self._state, channel=self.channel, data=payload.get("message", {}))

    async def defer_update(self, hidden: bool = False):
        base = {"type": 6}
        if hidden:
            base["data"] = {"flags": 64}

        await self.http.post_defer_response(payload=base)
        self.deferred = True
        return

    async def update(
            self,
            content=None,
            *,
            tts: bool = False,
            embed: discord.Embed = None,
            embeds: List[discord.Embed] = None,
            file: discord.File = None,
            files: List[discord.File] = None,
            allowed_mentions: discord.AllowedMentions = None,
            components: List[Union[ActionRow, Button, Selection]] = None
    ):
        if file is not None and files is not None:
            raise InvalidArgument()
        if embed is not None and embeds is not None:
            raise InvalidArgument()

        content = str(content) if content is not None else None
        if embed is not None:
            embeds = [embed]
        if embeds is not None:
            embeds = [embed.to_dict() for embed in embeds]
        if file:
            files = [file]
        if components is not None:
            components = [i.to_all_dict() if isinstance(i, ActionRow) else i.to_dict() for i in components]

        allowed_mentions = _allowed_mentions(self._state, allowed_mentions)
        payload = self._get_payload(
            content=content,
            embed=embeds,
            tts=tts,
            allowed_mentions=allowed_mentions,
            components=components,
        )

        if files:
            form = _files_to_form(files=files, payload=payload)
        else:
            form = None

        if not self.responded:
            if files:
                await self.defer_update()

            if self.deferred:
                await self.http.edit_message(
                    channel_id=self.channel.id, message_id=self.message.id,
                    payload=payload, form=form, files=files
                )
            else:
                await self.http.post_initial_components_response(payload=payload)
            self.responded = True
        else:
            await self.http.post_followup(payload=payload, form=form, files=files)

        if files:
            for i in files:
                i.close()
