#!/usr/bin/env python3

import math


def get_text_width(font, text, padding=6):
    """get the width of font text + padding"""
    change_width = (
        sum([font.CharacterWidth(ord(c)) for c in text]) + padding
    )

    return change_width


def find_center(canvas, text_width):
    return (canvas.width / 2) - math.floor(text_width / 2)
