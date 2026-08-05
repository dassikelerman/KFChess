import asyncio

from server.contracts import Participant
from server.participant_lifecycle import ParticipantLifecycle


class FakeMatchmaker:
    def __init__(self):
        self.cancel_search_calls = []

    def cancel_search(self, participant):
        self.cancel_search_calls.append(participant)


class FakeGameRoomRegistry:
    def __init__(self):
        self.remove_participant_calls = []

    async def remove_participant(self, participant):
        self.remove_participant_calls.append(participant)


def test_leaving_cancels_any_active_matchmaking_search_and_removes_the_participant_from_its_room():
    matchmaker = FakeMatchmaker()
    room_registry = FakeGameRoomRegistry()
    lifecycle = ParticipantLifecycle(matchmaker, room_registry)
    participant = Participant(connection="conn")

    asyncio.run(lifecycle.leave(participant))

    assert matchmaker.cancel_search_calls == [participant]
    assert room_registry.remove_participant_calls == [participant]
