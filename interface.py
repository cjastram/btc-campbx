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

import inspect
import math
import unirest
import time
import weakref
import yaml

from flask import Flask, render_template, redirect, url_for, jsonify
app = Flask(__name__)

ORDER_BOOK = None

class Order(dict):
    # dict so it pretty-prints and encodes to JSON easily
    # .attr so we can refer to .price, .side easily
    # object instead of plain dict so we can restrict types of values
    _keys = ["side", "price", "quantity", "exchange_id", "exchange_timestamp", "status", "link"]
    def __init__(self, side=None, price=None, quantity=None, exchange_id=None, exchange_timestamp=None, status=None, link=None):
        frame = inspect.currentframe()
        args, _, _, values = inspect.getargvalues(frame)
        args.pop(0)
        for key in args:
            self[key] = values[key]

    def __getitem__(self, key):
        if key not in self._keys:
            raise Exception("'" + key + "'" + " is not a valid key")
        try:
            return dict.__getitem__(self,key)
        except KeyError:
            return None

    def __setitem__(self, key, value):
        global ORDER_BOOK 

        if key == "side":
            if not value in ['bid', 'ask']: raise Exception("Side must be bid or ask")
        if key == "status":
            if not value in ['FANTASY', 'WORKING', 'FILLED', 'CANCELLED']: raise Exception("Invalid order status %s" % value)

        if key not in self._keys:
            raise Exception("'" + key + "'" + " is not a valid key")
        dict.__setitem__(self,key,value)
      
        # Save any changes immediately, in case of crash
        if ORDER_BOOK:
            ORDER_BOOK.saveOrderBook()
    
    def __getattr__(self, key): 
        return self[key]
    def __setattr__(self, key, value): 
        self[key] = value

order_book_filename = "order-book.yaml"

class Orders(list):
    trader = None

    def __init__(self, trader):
        global ORDER_BOOK
        self.trader = trader
        self.readOrderBook()
        ORDER_BOOK = self

    def readOrderBook(self):
        global order_book_filename
        del self[0:len(self)]
        try:
            f = file(order_book_filename, "r")
            loaded = yaml.load(f)
            for block in loaded:
                self.add(block)
            f.close()
        except IOError:
            print "--> Failed to load order book, starting anew"

    def saveOrderBook(self):
        global order_book_filename
        f = file(order_book_filename, "w")
        yaml.dump(self, f)
        f.close()

    def cleanup(self):
        remove = []
        i = 0
        while i < len(self):
            if self[i].status == "CANCELLED":
                remove.append(i)

            if self[i].status == "FILLED":
                all_filled = True
                ids = [self[i].exchange_id]
                linked = self.linked(self[i].exchange_id)
                if len(linked):
                    for order in linked:
                        if order.status == "FILLED":
                            ids.append(order.exchange_id)
                        else:
                            all_filled = False
                            break
                    if all_filled:
                        for j in range(0, len(self)):
                            if self[j].exchange_id in ids:
                                remove.append(j)
            i = i + 1
        remove.sort()
        remove.reverse()
        for r in remove:
            del(self[r])

    def bidsAtPrice(self, price):
        global ALLOWANCE
        bids = []
        for order in self:
            if order.side == "bid" and order.status != "CANCELLED":
                if order.price > (price - ALLOWANCE) and order.price < (price + ALLOWANCE):
                    bids.append(order)
        return bids
    
    def bidsUnderPrice(self, price):
        return [order for order in self if order.side == "bid" and order.price < price]
    
    def fantasies(self):
        return [order for order in self if order.status == "FANTASY"]
    
    def filledBids(self):
        return [order for order in self if order.side == "bid" and order.status == "FILLED"]
    
    def linked(self, id):
        return [order for order in self if order.link == id]

    def working(self):
        return [order for order in self if order.status == "WORKING"]

    def highestBidPrice(self):
        highest = 0
        for bid in [order for order in self if order.side == "bid"]:
            if bid.price > highest: highest = bid.price
        return highest
    
    def add(self, order):
        self.append(order)
        self.sort(key=lambda x: x.price)

ALLOWANCE = 0.01

class Algorithm:
    trader = None
    floor = 0
    ceiling = 0

    INTERVAL = 11
    TRADING_RANGE = 0.70    # % of ceiling
    POOL = 300              # USD to play with
    ALLOWANCE = 0.01
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
        #self.exchange(orders)

        ### Place orders
        #self.order(orders)

        ### Cancel excess orders
        ###self.cleanup(orders)

        ### Adjust existing
        # TODO

        ##for order in orders.order_book:
            ##if order.status == "WORKING":
                ##self.trader.cancel(order)
            ##print order
        
        #orders.cleanup()
        #orders.saveOrderBook()

    def hypothetical(self, order_book):
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

        floor = math.floor(ceiling * self.TRADING_RANGE)
        spread = self.INTERVAL
        self.floor = floor

        # No continuous variables!  We need to line up
        # the order grid in a predictable way.
        floor = floor - (floor % self.INTERVAL)
        
        # -- Cancel bids below floor ----------------- #
        for bid in order_book.bidsUnderPrice(floor):   #
            if bid.status == "WORKING":                #
                self.trader.cancel(bid)                #
        # -------------------------------------------- #

        bid = floor
        bids = []
        while bid < ceiling:
            bids.append(bid)
            bid = bid + self.INTERVAL

        balances = self.trader.balances()
        print balances
        available_fiat = balances["usd-total"]
        if self.POOL < available_fiat: available_fiat = self.POOL

        fiat = available_fiat / len(bids)

        for bid in bids:
            qty = fiat / bid
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
        
        # Cancel bids 

    def exchange(self, order_book):
        global ALLOWANCE
        exchange_orders = self.trader.orders()

        # Discover any orders placed but not recorded, that may 
        # match with fantasy orders (i.e. don't double-bid).
        for remote in exchange_orders:
            for local in order_book.fantasies():
                if local.price > (remote["price"] - self.ALLOWANCE) and local.price < (remote["price"] + self.ALLOWANCE):
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
                ask_price = bid_price + self.INTERVAL
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

    #def cleanup(self, order_book):
        #for bid in order_book.bidsUnderPrice(self.floor):
            #self.trader.cancel(bid)

class CampBX:
    timestamp = None
    login = "X"
    password = "X"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json; charset=UTF-8'
    }
    def __init__(self):
        self.timestamp = time.time()
    def __wait(self):
        while time.time() < self.timestamp:
            time.sleep(0.1)
    def __timestamp(self):
        self.timestamp = time.time()
    def cancel(self, order):
        print "--> Cancelling order"
        print order
        if order.status == "FANTASY":
            order.status = "CANCELLED"
        else:
            params = {
                'user': self.login,
                'pass': self.password,
                'Type': "Buy" if order.side == "bid" else "Sell",
                'OrderID': order.exchange_id
            }
            url = "https://CampBX.com/api/tradecancel.php"
            args = ""
            for key, value in params.iteritems():
                if len(args): args = args + "&"
                args = args + "%s=%s" % (key, value)
            url = url + "?" + args
            self.__wait()
            response = unirest.post(url, headers=self.headers, params={})
            self.__timestamp()
            #if "Error" in response.body:
                #raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
            order.status = "CANCELLED"
    
    def place(self, order):
        print "--> Placing %s for %f at %f" % (order.side, order.quantity, order.price)
        params = {
            'user': self.login,
            'pass': self.password,
            'TradeMode': "QuickBuy" if order.side == "bid" else "QuickSell",
            'Quantity': order.quantity,
            'Price': order.price
        }
        url = "https://campbx.com/api/tradeenter.php"
        args = ""
        for key, value in params.iteritems():
            if len(args): args = args + "&"
            args = args + "%s=%s" % (key, value)
        url = url + "?" + args
        self.__wait()
        response = unirest.post(url, headers=self.headers, params={})
        self.__timestamp()
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        if not "Success" in response.body:
            raise Exception("Bitcoin exchange API failed to return order success!")
        order.exchange_id = response.body["Success"]
        if order.exchange_id == "0":
            order.status = "FILLED"
        else:
            order.status = "WORKING"
            for remote in self.orders():
                if remote["id"] == order.exchange_id:
                    order.exchange_timestamp = remote["timestamp"]

    def tick(self):
        self.__wait()
        response = unirest.post("http://campbx.com/api/xticker.php") #, self.headers, {})
        self.__timestamp()
        return { 'bid': float(response.body["Best Bid"]), 'ask': float(response.body["Best Ask"]) }

    def orders(self):
        url = "https://campbx.com/api/myorders.php?user=%s&pass=%s" % (self.login, self.password)
        self.__wait()
        response = unirest.post(url, headers=self.headers, params={})
        self.__timestamp()
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        
        orders = []
        for order_type, exchange_orders in response.body.iteritems():
            order_type = order_type.lower()
            for exchange_order in exchange_orders:
                if not "Price" in exchange_order: continue
                orders.append({
                    "id": exchange_order["Order ID"],
                    "side": order_type.lower(), 
                    "price": float(exchange_order["Price"]),
                    "amount": float(exchange_order["Quantity"]),
                    "timestamp": exchange_order["Order Entered"],
                    })
        return orders

    def balances(self):
        url = "https://campbx.com/api/myfunds.php?user=%s&pass=%s" % (self.login, self.password)
        self.__wait()
        response = unirest.post(url, headers=self.headers, params={})
        self.__timestamp()
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        return { "usd-liquid": response.body["Liquid USD"],
                 "usd-total":  response.body["Total USD"],
                 "btc-liquid": response.body["Liquid BTC"],
                 "btc-total":  response.body["Total BTC"] }

class Log:
    def __init__(self):
        print "--> Initializing log..."

class Parameters:
    _filename = "settings.yaml"
    def _read(self):
        f = open(self._filename, 'r')
        temp = yaml.safe_load(f)
        f.close()
        return temp
    def algorithm(self, key, value=None):
        d = self._read()
        return d["algorithm"][key]
    def group(self, key):
        d = self._read()
        return d[key]
        
SETTINGS = Parameters()
TRADER = CampBX()

@app.route("/")
def hello():
    global TRADER

    order_book = Orders(TRADER)
        
    f = open("templates/index.html")
    d = f.read()
    f.close()
    return d
    #return render_template('index.html', 
        #order_book=order_book)

@app.route("/algo")
def algo():
    global TRADER
    order_book = Orders(TRADER)
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
