from lunora.calc.chinese import calculate_chinese
from lunora.calc.numerology import calculate_numerology
from lunora.calc.types import BirthData, FullChart
from lunora.calc.vedic import calculate_vedic
from lunora.calc.western import calculate_western


def calculate(data: BirthData) -> FullChart:
    return FullChart(
        western=calculate_western(data),
        vedic=calculate_vedic(data),
        chinese=calculate_chinese(data),
        numerology=calculate_numerology(data),
    )
