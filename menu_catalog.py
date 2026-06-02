"""Curated menu/category templates for realistic menus-flow provisioning."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class MenuCatalogEntry:
    category_name: str
    menu_name: str
    description: str
    price: float
    ingredients: str


TEMPLATES: list[MenuCatalogEntry] = [
    MenuCatalogEntry(
        "Drinks",
        "Sparkling Yuzu",
        "Citrus soda with yuzu.",
        450.0,
        "yuzu, sparkling water",
    ),
    MenuCatalogEntry(
        "Drinks",
        "Iced Hibiscus Tea",
        "Light floral iced tea.",
        380.0,
        "hibiscus, water, cane sugar",
    ),
    MenuCatalogEntry(
        "Small Plates",
        "Crispy Yam Bites",
        "Golden fried yam with pepper dip.",
        650.0,
        "yam, pepper, vegetable oil",
    ),
    MenuCatalogEntry(
        "Small Plates",
        "Pepper Soup Cup",
        "Spiced broth with tender meat.",
        720.0,
        "pepper, stock, goat meat",
    ),
    MenuCatalogEntry(
        "Mains",
        "Jollof Rice Box",
        "Smoky jollof with grilled chicken.",
        1450.0,
        "rice, tomato, chicken, spices",
    ),
    MenuCatalogEntry(
        "Mains",
        "Grilled Suya Plate",
        "Spiced skewers with onions.",
        1680.0,
        "beef, suya spice, onion",
    ),
    MenuCatalogEntry(
        "Sides",
        "Plantain Chips",
        "Sweet plantain crisps.",
        420.0,
        "plantain, salt",
    ),
    MenuCatalogEntry(
        "Sides",
        "Coleslaw Cup",
        "Creamy cabbage slaw.",
        350.0,
        "cabbage, carrot, dressing",
    ),
    MenuCatalogEntry(
        "Desserts",
        "Coconut Puff",
        "Flaky pastry with coconut filling.",
        480.0,
        "flour, coconut, butter",
    ),
    MenuCatalogEntry(
        "Desserts",
        "Mango Sorbet",
        "Chilled mango dessert.",
        520.0,
        "mango, water, sugar",
    ),
]


def pick_entry() -> MenuCatalogEntry:
    return random.choice(TEMPLATES)


def pick_entry_for_category(name: str) -> MenuCatalogEntry:
    matches = [entry for entry in TEMPLATES if entry.category_name.lower() == name.lower()]
    return random.choice(matches) if matches else pick_entry()
