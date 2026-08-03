from lunora.llm.safety import Category, classify_input
from lunora.llm.validator import validate_output


class TestClassifyInput:
    def test_normal(self):
        assert classify_input("Расскажи про мою карту") == Category.NORMAL

    def test_medical(self):
        assert classify_input("Будет ли у меня болезнь?") == Category.MEDICAL
        assert classify_input("Стоит ли идти к врачу?") == Category.MEDICAL

    def test_crisis(self):
        assert classify_input("Не хочу жить") == Category.CRISIS
        assert classify_input("Думаю покончить") == Category.CRISIS

    def test_crisis_priority_over_medical(self):
        assert classify_input("Не хочу жить, болит всё") == Category.CRISIS

    def test_financial(self):
        assert classify_input("Стоит ли вложить в криптовалюту?") == Category.FINANCIAL
        assert classify_input("Когда покупать акции?") == Category.FINANCIAL


class TestValidateOutput:
    def test_valid(self):
        text = "🔮 Западная\n🪷 Ведическая\n🐉 Китайская\n🔢 Нумерология\n✨ Итог\n" + "x" * 200
        ok, reason = validate_output(text)
        assert ok

    def test_forbidden(self):
        text = "🔮🪷🐉🔢✨ Ты умрёшь через год " + "x" * 200
        ok, reason = validate_output(text)
        assert not ok
        assert "запрещённые" in reason

    def test_missing_section(self):
        text = "🔮 Западная\n🪷 Ведическая\n" + "x" * 200
        ok, reason = validate_output(text)
        assert not ok
        assert "секции" in reason

    def test_too_short(self):
        text = "🔮🪷🐉🔢✨ Коротко"
        ok, reason = validate_output(text)
        assert not ok
        assert "короткий" in reason
