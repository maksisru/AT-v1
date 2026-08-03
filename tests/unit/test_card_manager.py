from gui.card_manager import CardData, CardManager


def test_card_manager_persists_order_and_state(tmp_path):
    path = tmp_path / "workspace.json"
    manager = CardManager(path)
    first = manager.create_card(data={"symbol": "BTCUSDT", "gross_spread": 1.2})
    second = manager.create_card(data={"symbol": "ETHUSDT"})

    manager.update_card_state(second.card_id, pinned=True, size="LARGE", collapsed=True)
    order = manager.reorder_cards([first.card_id, second.card_id])
    assert order == [second.card_id, first.card_id]

    manager.save_workspace()
    restored = CardManager(path)
    cards = restored.load_workspace()

    assert [card.card_id for card in cards] == [second.card_id, first.card_id]
    assert cards[0].pinned is True
    assert cards[0].size == "LARGE"
    assert cards[0].collapsed is True


def test_update_card_skips_unchanged_data_and_keeps_history(tmp_path):
    manager = CardManager(tmp_path / "workspace.json")
    card = manager.create_card(data={"symbol": "SOLUSDT"})

    assert manager.update_card(card.card_id, CardData(symbol="SOLUSDT")) is False
    assert manager.update_card(card.card_id, CardData(symbol="SOLUSDT", net_edge=0.5)) is True
    assert manager.get_card(card.card_id).history[-1]["net_edge"] == 0.5


def test_multiple_workspaces_are_isolated(tmp_path):
    manager = CardManager(tmp_path / "workspace.json")
    scalping = manager.create_card("Scalping", {"symbol": "BTCUSDT"})
    funding = manager.create_card("Funding", {"symbol": "XRPUSDT"})

    assert manager.switch_workspace("Scalping") == [scalping]
    assert manager.switch_workspace("Funding") == [funding]
