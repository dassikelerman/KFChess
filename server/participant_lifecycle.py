"""ParticipantLifecycle: what happens when a participant leaves, in one place.

Leaving touches two independent collaborators - Matchmaker (drop them from the queue
if they were waiting) and GameRoomRegistry (drop them from their room if they were
seated) - a participant is only ever in one of those places at a time, but nothing
enforces that, so both are always attempted rather than the caller having to know
which one applies. Previously this lived as an ad hoc closure inside
server/ws_server.py's main(); giving it a name and a single owner means the connection
layer only ever calls one coroutine, and never has to know Matchmaker exists.
"""


class ParticipantLifecycle:
    def __init__(self, matchmaker, room_registry):
        self._matchmaker = matchmaker
        self._room_registry = room_registry

    async def leave(self, participant):
        self._matchmaker.cancel_search(participant)
        await self._room_registry.remove_participant(participant)
