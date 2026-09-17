name: Kozelets News Bot

on:
  schedule:
    - cron: "*/5 * * * *"   # кожні 5 хвилин
  workflow_dispatch:

jobs:
  run-bot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests googlenewsdecoder tzdata

      - name: Run bot
        env:
          BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
          CHANNEL: ${{ secrets.CHANNEL }}
        run: python main.py
