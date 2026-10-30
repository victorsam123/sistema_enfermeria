"""Cálculo inclusivo de reposos, independiente de otras políticas."""


def rest_days(start, end):
    if start is None or end is None:
        raise ValueError('Completa la fecha desde y la fecha hasta.')
    if end < start:
        raise ValueError('La fecha hasta no puede ser anterior a la fecha desde.')
    return (end - start).days + 1
