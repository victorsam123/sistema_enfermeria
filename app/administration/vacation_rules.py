"""Regla inicial: días calendario inclusivos. Punto único de cálculo Python."""


def vacation_days(start, end):
    if start is None or end is None:
        raise ValueError('Completa ambas fechas de vacaciones.')
    if end < start:
        raise ValueError('La fecha de término no puede ser anterior a la fecha de inicio.')
    return (end - start).days + 1
