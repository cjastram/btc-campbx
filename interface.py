#!/usr/bin/env python
#
#   This tool trades bitcoin on the CampBX platform with a focus on Flask.
#   Copyright (C) 2013 Christopher Jastram
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import hashlib
import hmac
import inspect
import json
import math
import unirest
import time
import weakref
import yaml

from exchanges.mtgox import MtGox
from utilities.miscellaneous import Log, Settings
from utilities.accounting import Order, Orders

from flask import Flask, render_template, redirect, url_for, jsonify
app = Flask(__name__)

ORDER_BOOK = None

class Algorithm:
    trader = None
    floor = 0
    ceiling = 0

    TOLERANCE = 0.02       # % variance in BTC purchase quantities
    
    def __init__(self, trader, order_book):
        self.trader = trader
        self.order_book = order_book

    def run(self):
        orders = self.order_book

        ### Clear filled pairs
        # TODO

        ### Set up hypothetical orders, both bids and asks
        self.hypothetical(orders)

        ### Evaluate filled orders
        self.exchange(orders)

        ### Place orders
        self.order(orders)

        ### Cancel excess orders
        self.cleanup(orders)

        ### Adjust existing
        # TODO
 
        ### This little block of code will cancel all working orders...
        ### use with care!
        ##for order in orders.order_book:
            ##if order.status == "WORKING":
                ##self.trader.cancel(order)
            ##print order
        
        orders.cleanup()
        orders.saveOrderBook()

    def hypothetical(self, order_book):
        global SETTINGS
        interval = SETTINGS.algorithm("interval")
        allowance = SETTINGS.algorithm("allowance")
        trading_range = SETTINGS.algorithm("tradingRange")
        pool = SETTINGS.algorithm("pool")
        tick = self.trader.tick()

        # Figure out price ceiling, from either tick or highest unpaired bid,
        # depending on which is higher.  This way, the ceiling remains fairly 
        # static and we don't get a shrinking ceiling as the price reduces, 
        # thereby resulting is massive increases in bid size as the total 
        # trading spread decreases.
        ceiling = tick["bid"]
        highest_bid_price = order_book.highestBidPrice()
        if ceiling < highest_bid_price: ceiling = highest_bid_price
        self.ceiling = ceiling

        floor = math.floor(ceiling * trading_range)
        spread = interval
        self.floor = floor

        # No continuous variables!  We need to line up
        # the order grid in a predictable way.
        floor = floor - (floor % interval)
        
        # -- Cancel bids below floor ----------------- #
        for bid in order_book.bidsUnderPrice(floor):   #
            if bid.status == "WORKING":                #
                self.trader.cancel(bid)                #
        # -------------------------------------------- #

        bid = floor
        bids = []
        while bid < ceiling:
            bids.append(bid)
            bid = bid + interval

        balances = self.trader.balances()
        available_fiat = balances["usd-total"]
        if pool < available_fiat: available_fiat = pool

        fiat = available_fiat / len(bids)

        for bid in bids:
            qty = round(fiat / bid, 4)
            parameters = {
                "fiat": fiat,
                "btc": qty,
                "bid": bid}

            # - Cancel orders for too much / too little btc ------- #
            existing = order_book.bidsAtPrice(bid)                  #
#            existing_qty = 0                                        #
#            for order in existing:                                  #
#                existing_qty = existing_qty + order.quantity        #
#            min = qty * (1-self.TOLERANCE)                          #
#            max = qty * (1+self.TOLERANCE)                          #
#            if existing_qty < min or existing_qty > max:            #
#                for order in existing:                              #
#                    if order.status == "WORKING":                   #
#                        self.trader.cancel(order)                   #
#                existing = order_book.bidsAtPrice(bid)              #
            # ----------------------------------------------------- #

            if not len(existing):
                order = Order(side="bid", price=bid, quantity=qty, status="FANTASY")
                order_book.add(order)
                print "--> Added fantasy order at %f" % bid

        # Cancel fantasy bids that don't line up with the interval
        for fantasy_bid in order_book.fantasyBids():
            remove = True
            for allowed_bid in bids:
                if self._tolerance(allowed_bid, fantasy_bid.price):
                    remove = False
            if remove:
                self.trader.cancel(fantasy_bid)
    
    def _tolerance(self, a, b):
        global SETTINGS
        allowance = SETTINGS.algorithm("allowance")
        return (a > (b - allowance) and a < (b + allowance))

    def exchange(self, order_book):
        global SETTINGS
        interval = SETTINGS.algorithm("interval")
        allowance = SETTINGS.algorithm("allowance")
        exchange_orders = self.trader.orders()

        # Discover any orders placed but not recorded, that may 
        # match with fantasy orders (i.e. don't double-bid).
        for remote in exchange_orders:
            for local in order_book.fantasies():
                if self._tolerance(local.price, remote["price"]):
                    local.exchange_id = remote["id"]
                    local.exchange_timestamp = remote["timestamp"]
                    local.quantity = remote["amount"]
                    local.status = "WORKING"
        
        # If an order is working but no longer exists on exchange, 
        # this means the order was filled: act accordingly.
        for local in order_book.working():
            if not len([remote for remote in exchange_orders if remote["id"] == local.exchange_id]):
                local.status = "FILLED"
        
        # Look up filled bids, place corresponding asks.
        # This may deserve its own function.
        for bid in order_book.filledBids():
            if not len(order_book.linked(bid.exchange_id)):
                bid_price = bid.price
                ask_price = bid_price + interval
                bid_usd = bid.quantity * bid_price
                ask_usd = bid.quantity * ask_price
                ask_qty = bid_usd / ask_price

                # We are going to sell however much of the original quantity
                # in order to replenish USD.
                ask = Order(side="ask", price=ask_price, quantity=ask_qty, status="FANTASY", link=bid.exchange_id)
                order_book.add(ask)
        
        ### TODO Filter for user-placed orders

        ### TODO Alert if orders are found that do not match
        ###      either the order book or user-placed orders
                    
    def order(self, order_book):
        for order in order_book.fantasies():
            self.trader.place(order)

    def cleanup(self, order_book):
        pass
        #for bid in order_book.bidsUnderPrice(self.floor):
            #self.trader.cancel(bid)

SETTINGS = Settings()
TRADER = MtGox(settings=SETTINGS)

@app.route("/")
def hello():
    global SETTINGS
    global TRADER

    order_book = Orders(TRADER, SETTINGS)
        
    f = open("templates/index.html")
    d = f.read()
    f.close()
    return d
    #return render_template('index.html', 
        #order_book=order_book)

@app.route("/orders")
def orders():
    global SETTINGS
    global TRADER
    order_book = Orders(TRADER, SETTINGS)
    
    # not sure why jsonify() does not work here...
    return json.dumps(order_book) 

@app.route("/algo")
def algo():
    global SETTINGS
    global TRADER
    order_book = Orders(TRADER, SETTINGS)
    algo = Algorithm(TRADER, order_book)
    algo.run()
    return redirect("/") 

@app.route("/tick")
def tick():
    global TRADER
    ret = TRADER.tick()
    ret.update(TRADER.balances())
    return jsonify(ret)

@app.route("/settings/algorithm")
def settings():
    global SETTINGS
    return jsonify(SETTINGS.group("algorithm"))

if __name__ == "__main__":
    app.debug = True
    app.run()
