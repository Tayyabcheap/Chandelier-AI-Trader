"""
execution/discord_bot.py
Fully interactive two-way Discord Bot.
"""

import discord
from discord import app_commands
import asyncio
from config.settings import settings
from core.logger import get_logger
import threading
import os
import certifi

logger = get_logger("DiscordBot")

class TradeDropdown(discord.ui.Select):
    def __init__(self, connector):
        self.connector = connector
        options = []
        positions = self.connector.get_open_positions()
        
        if not positions:
            options.append(discord.SelectOption(label="No Open Trades", description="You have no active positions.", value="none"))
        else:
            for pos in positions:
                sym = pos["symbol"]
                ticket = pos["ticket"]
                profit = pos["profit"]
                typ = "BUY" if pos["type"] == 0 else "SELL"
                icon = "🟢" if profit >= 0 else "🔴"
                options.append(
                    discord.SelectOption(
                        label=f"{typ} {sym} [#{ticket}]", 
                        description=f"{icon} PnL: ${profit:.2f}",
                        value=str(ticket)
                    )
                )

        super().__init__(placeholder="Select a trade to close...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No trades available to close.", ephemeral=True)
            return
            
        ticket = int(self.values[0])
        # Run close in background so it doesn't block async loop
        threading.Thread(target=self.connector.close_position, args=(ticket,), daemon=True).start()
        await interaction.response.send_message(f"✅ Sent kill signal to MT5 for ticket #{ticket}!", ephemeral=True)

class CloseTradeView(discord.ui.View):
    def __init__(self, connector):
        super().__init__()
        self.add_item(TradeDropdown(connector))


class ExnessDiscordBot(discord.Client):
    def __init__(self, connector, settings):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.connector = connector
        self.s = settings
        self.ticker_message = None

    async def setup_hook(self):
        await self.tree.sync()
        self.bg_task = self.loop.create_task(self.live_ticker_loop())

    async def on_ready(self):
        logger.info(f"Discord Interactive Bot connected as {self.user}!")

    async def live_ticker_loop(self):
        """Continuously update a live status message if requested."""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                if self.ticker_message:
                    embed = self._build_status_embed()
                    await self.ticker_message.edit(embed=embed)
            except Exception as e:
                logger.error(f"Live ticker error: {e}")
                self.ticker_message = None # Reset if message deleted
            await asyncio.sleep(5)

    def _build_status_embed(self):
        positions = self.connector.get_open_positions()
        info = self.connector.get_account_info()
        
        embed = discord.Embed(
            title="📊 Live Trading Terminal", 
            color=0x2ECC71 if info["profit"] >= 0 else 0xE74C3C
        )
        embed.add_field(name="Balance", value=f"`${info['balance']:.2f}`", inline=True)
        embed.add_field(name="Total Floating PnL", value=f"`${info['profit']:+.2f}`", inline=True)
        
        if not positions:
            embed.description = "Waiting for trading signals... 😴"
        else:
            desc = ""
            for p in positions:
                sym = p["symbol"]
                typ = "BUY" if p["type"] == 0 else "SELL"
                profit = p["profit"]
                icon = "🟢" if profit >= 0 else "🔴"
                
                # Check for manual tag
                tag = " 🏷️ [MANUAL]" if p.get("comment", "").startswith("manual") else ""
                desc += f"{icon} **{typ} {sym}** `[#{p['ticket']}]` → **${profit:.2f}**{tag}\n"
            embed.description = desc
            
        return embed


def run_discord_bot(connector, settings):
    if not settings.DISCORD_BOT_TOKEN:
        logger.warning("No DISCORD_BOT_TOKEN found. Interactive bot is disabled.")
        return
        
    bot = ExnessDiscordBot(connector, settings)

    @bot.tree.command(name="status", description="Get a live snapshot of open trades and account balance.")
    async def status_cmd(interaction: discord.Interaction):
        embed = bot._build_status_embed()
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="ticker", description="Spawn a live-updating trade ticker in this channel.")
    async def ticker_cmd(interaction: discord.Interaction):
        embed = bot._build_status_embed()
        await interaction.response.send_message("Launching Live Ticker...")
        msg = await interaction.original_response()
        bot.ticker_message = msg

    @bot.tree.command(name="close", description="Close an active trade via interactive menu.")
    async def close_cmd(interaction: discord.Interaction):
        view = CloseTradeView(bot.connector)
        await interaction.response.send_message("Select a trade to close:", view=view, ephemeral=True)

    @bot.tree.command(name="block", description="Block a currency pair from trading.")
    @app_commands.choices(symbol=[app_commands.Choice(name=s, value=s) for s in settings.SYMBOLS[:25]])
    async def block_cmd(interaction: discord.Interaction, symbol: app_commands.Choice[str]):
        sym = symbol.value
        if sym not in bot.s.BLOCKED_SYMBOLS:
            bot.s.BLOCKED_SYMBOLS.append(sym)
            bot.s.update_setting("BLOCKED_SYMBOLS", ",".join(bot.s.BLOCKED_SYMBOLS), list)
            await interaction.response.send_message(f"🛡️ **{sym}** added to blocklist.")
        else:
            await interaction.response.send_message(f"⚠️ **{sym}** is already blocked.")

    @bot.tree.command(name="unblock", description="Remove a currency pair from the blocklist.")
    @app_commands.choices(symbol=[app_commands.Choice(name=s, value=s) for s in settings.SYMBOLS[:25]])
    async def unblock_cmd(interaction: discord.Interaction, symbol: app_commands.Choice[str]):
        sym = symbol.value
        if sym in bot.s.BLOCKED_SYMBOLS:
            bot.s.BLOCKED_SYMBOLS.remove(sym)
            bot.s.update_setting("BLOCKED_SYMBOLS", ",".join(bot.s.BLOCKED_SYMBOLS), list)
            await interaction.response.send_message(f"✅ **{sym}** removed from blocklist. Trading allowed.")
        else:
            await interaction.response.send_message(f"⚠️ **{sym}** is not in the blocklist.")

    @bot.tree.command(name="settings", description="Change Daily PnL limits and Max Trades.")
    async def settings_cmd(interaction: discord.Interaction, profit_target: float = None, loss_limit: float = None, max_trades: int = None):
        changes = []
        if profit_target is not None:
            bot.s.update_setting("DAILY_PROFIT_TARGET_PCT", str(profit_target), float)
            changes.append(f"Target: +{profit_target}%")
        if loss_limit is not None:
            bot.s.update_setting("DAILY_LOSS_LIMIT_PCT", str(loss_limit), float)
            changes.append(f"Loss Limit: -{loss_limit}%")
        if max_trades is not None:
            bot.s.update_setting("MAX_OPEN_TRADES", str(max_trades), int)
            changes.append(f"Max Trades: {max_trades}")
            
        if changes:
            await interaction.response.send_message(f"✅ **Settings Updated:**\n" + "\n".join(changes))
        else:
            await interaction.response.send_message("⚠️ No settings provided. Usage: `/settings profit_target: 5.0`", ephemeral=True)

    @bot.tree.command(name="trade", description="Manually open a trade (Bypasses Limits). Supports multiple TPs.")
    @app_commands.choices(direction=[
        app_commands.Choice(name="BUY", value="BUY"),
        app_commands.Choice(name="SELL", value="SELL")
    ])
    async def trade_cmd(interaction: discord.Interaction, symbol: str, direction: app_commands.Choice[str], sl: float, tp1: float, tp2: float = 0.0, lot: float = 0.1):
        sym = symbol.upper()
        dir_val = direction.value
        await interaction.response.defer()
        
        try:
            if tp2 > 0.0:
                half_lot = max(0.01, round(lot / 2.0, 2))
                
                # Ticket 1 (TP1)
                t1 = bot.connector.open_position(sym, dir_val, half_lot, sl, tp1, comment="manual_tp1")
                # Ticket 2 (TP2)
                t2 = bot.connector.open_position(sym, dir_val, half_lot, sl, tp2, comment="manual_tp2")
                
                if t1 and t2:
                    msg = f"🚀 **MANUAL DUAL-TRADE OPENED**\n**{dir_val} {sym}**\nSplit Lot: `{half_lot}` x2\nSL: `{sl}`\nTP1: `{tp1}` [#{t1}]\nTP2: `{tp2}` [#{t2}]"
                elif t1:
                    msg = f"⚠️ **PARTIAL SUCCESS**\nTP1 Ticket opened [#{t1}], but TP2 Ticket failed."
                else:
                    msg = f"❌ **FAILED**\nCould not open trades. Check MT5 connection and parameters."
            else:
                # Single Ticket
                t1 = bot.connector.open_position(sym, dir_val, lot, sl, tp1, comment="manual_trade")
                if t1:
                    msg = f"🚀 **MANUAL TRADE OPENED**\n**{dir_val} {sym}**\nLot: `{lot}`\nSL: `{sl}`\nTP: `{tp1}`\nTicket: `#{t1}`"
                else:
                    msg = f"❌ **FAILED**\nCould not open trade. Check MT5 connection and parameters."
                    
            await interaction.followup.send(msg)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error opening manual trade: {e}")

    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.start(settings.DISCORD_BOT_TOKEN))
    except Exception as e:
        logger.error(f"Discord bot thread crashed: {e}")
