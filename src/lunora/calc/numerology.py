from lunora.calc.types import BirthData, NumerologyChart, PythagorasSquare


def _digit_root(n: int) -> int:
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(d) for d in str(n))
    return n


def _life_path(d) -> int:
    total = sum(int(c) for c in d.strftime("%d%m%Y"))
    return _digit_root(total)


def _pythagoras_square(d) -> PythagorasSquare:
    digits = [int(c) for c in d.strftime("%d%m%Y")]
    s1 = sum(digits)
    s2 = _digit_root(s1)
    s3 = s1 - 2 * digits[0]
    s4 = _digit_root(abs(s3))
    all_digits = (
        list(d.strftime("%d%m%Y"))
        + list(str(s1))
        + list(str(s2))
        + list(str(abs(s3)))
        + list(str(s4))
    )
    cells = {i: 0 for i in range(1, 10)}
    for ch in all_digits:
        n = int(ch)
        if 1 <= n <= 9:
            cells[n] += 1
    return PythagorasSquare(cells=cells, working_numbers=(s1, s2, abs(s3), s4))


def calculate_numerology(data: BirthData) -> NumerologyChart:
    d = data.birth_date
    return NumerologyChart(
        life_path=_life_path(d),
        birthday_number=_digit_root(d.day),
        pythagoras=_pythagoras_square(d),
    )
