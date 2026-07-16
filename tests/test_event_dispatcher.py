from events.dispatcher import EventDispatcher


class Ping:
    pass


class Pong:
    pass


def test_publish_calls_every_subscriber_of_that_event_type():
    dispatcher = EventDispatcher()
    received_a = []
    received_b = []
    dispatcher.subscribe(Ping, received_a.append)
    dispatcher.subscribe(Ping, received_b.append)

    event = Ping()
    dispatcher.publish(event)

    assert received_a == [event]
    assert received_b == [event]


def test_publish_does_not_call_subscribers_of_a_different_event_type():
    dispatcher = EventDispatcher()
    received = []
    dispatcher.subscribe(Ping, received.append)

    dispatcher.publish(Pong())

    assert received == []


def test_publish_with_no_subscribers_is_a_no_op():
    dispatcher = EventDispatcher()
    dispatcher.publish(Ping())  # must not raise


def test_unsubscribe_with_the_same_callback_object_stops_delivery():
    dispatcher = EventDispatcher()
    received = []

    def callback(event):
        received.append(event)

    dispatcher.subscribe(Ping, callback)
    dispatcher.unsubscribe(Ping, callback)
    dispatcher.publish(Ping())

    assert received == []


def test_unsubscribe_an_unknown_callback_is_a_no_op():
    dispatcher = EventDispatcher()
    dispatcher.unsubscribe(Ping, lambda event: None)  # must not raise


def test_a_callback_can_unsubscribe_itself_during_publish_without_breaking_iteration():
    dispatcher = EventDispatcher()
    received = []

    def self_removing(event):
        received.append(event)
        dispatcher.unsubscribe(Ping, self_removing)

    other_received = []
    dispatcher.subscribe(Ping, self_removing)
    dispatcher.subscribe(Ping, other_received.append)

    dispatcher.publish(Ping())
    dispatcher.publish(Ping())

    assert len(received) == 1  # unsubscribed itself after the first publish
    assert len(other_received) == 2  # unaffected by the other subscriber leaving
