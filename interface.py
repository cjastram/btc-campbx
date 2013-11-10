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
import yaml
from flask import Flask
from flask import render_template
app = Flask(__name__)

class Order(dict):
    # dict so it pretty-prints and encodes to JSON easily
    # .attr so we can refer to .price, .side easily
    # object instead of plain dict so we can restrict types of values
    _keys = ["side", "price", "quantity", "exchange_id", "exchange_timestamp", "status"]
    def __init__(self, side=None, price=None, quantity=None, exchange_id=None, exchange_timestamp=None, status=None):
        frame = inspect.currentframe()
        args, _, _, values = inspect.getargvalues(frame)
        args.pop(0)
        for key in args:
            self[key] = values[key]

    def __getitem__(self, key):
        if key not in self._keys:
            raise Exception("'" + key + "'" + " is not a valid key")
        return dict.__getitem__(self,key)

    def __setitem__(self, key, value):
        if key == "side":
            if not value in ['bid', 'ask']: raise Exception("Side must be bid or ask")
        if key == "status":
            if not value in ['FANTASY', 'WORKING', 'FILLED', 'CANCELLED']: raise Exception("Invalid order status %s" % value)

        if key not in self._keys:
            raise Exception("'" + key + "'" + " is not a valid key")
        dict.__setitem__(self,key,value)
    
    def __getattr__(self, key): return self[key]
    def __setattr__(self, key, value): self[key] = value

class Orders(list):
    order_book_filename = "order-book.yaml"
    order_book = []
    trader = None

    ALLOWANCE = 0.01

    def __init__(self, trader):
        self.trader = trader
        self.readOrderBook()

    def readOrderBook(self):
        self.order_book = []
        try:
            f = file(self.order_book_filename, "r")
            self.order_book = yaml.load(f)
            if self.order_book is None:
                self.order_book = []
            f.close()
        except IOError:
            print "--> Failed to load order book, starting anew"

    def saveOrderBook(self):
        f = file(self.order_book_filename, "w")
        yaml.dump(self.order_book, f)
        f.close()

    def cleanup(self):
        self.order_book = [order for order in self.order_book if order.status != "CANCELLED"]

    def bidsAtPrice(self, price):
        bids = []
        for order in self.order_book:
            if order.side == "bid":
                if order.price > (price - self.ALLOWANCE) and order.price < (price + self.ALLOWANCE):
                    bids.append(order)
        return bids
    
    def fantasies(self):
        return [order for order in self.order_book if order.status == "FANTASY"]
    
    def fantasyBids(self):
        return [order for order in self.order_book if order.side == "bid" and order.status == "FANTASY"]

    def add(self, order):
        self.order_book.append(order)
        self.order_book.sort(key=lambda x: x.price)

class Algorithm:
    trader = None

    INTERVAL = 7
    TRADING_RANGE = 0.70    # % of ceiling
    POOL = 400              # USD to play with
    ALLOWANCE = 0.01
    
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
        #self.bids(orders)

        ### Cancel excess
        # TODO

        ### Adjust existing
        # TODO

        #for order in orders.order_book:
            #if order.status == "WORKING":
                #self.trader.cancel(order)
            #print order
        orders.cleanup()
        orders.saveOrderBook()

    def hypothetical(self, order_book):
        tick = self.trader.tick()

        # Figure out price ceiling, from either tick or highest unpaired bid,
        # depending on which is higher.  This way, the ceiling remains fairly 
        # static and we don't get a shrinking ceiling as the price reduces, 
        # thereby resulting is massive increases in bid size as the total 
        # trading spread decreases.
        ceiling = tick["ask"]
        #order_book.highestBidPrice()

        floor = math.floor(ceiling * self.TRADING_RANGE)
        spread = self.INTERVAL

        # No continuous variables!  We need to line up
        # the order grid in a predictable way.
        floor = floor - (floor % self.INTERVAL)

        bid = floor
        bids = []
        while bid < ceiling:
            bids.append(bid)
            bid = bid + self.INTERVAL

        balances = self.trader.balances()
        available_fiat = balances["usd-total"]
        if self.POOL < available_fiat: available_fiat = self.POOL

        fiat = available_fiat / len(bids)

        for bid in bids:
            qty = fiat / bid
            parameters = {
                "fiat": fiat,
                "btc": qty,
                "bid": bid}
            if not len(order_book.bidsAtPrice(bid)):
                order = Order(side="bid", price=bid, quantity=qty, status="FANTASY")
                order_book.add(order)
                print "--> Added fantasy order at %f" % bid

    def exchange(self, order_book):
        # Discover any orders placed but not recorded, that may 
        # match with fantasy orders (i.e. don't double-bid).
        for remote in self.trader.orders():
            for local in order_book.fantasies():
                if local.price > (remote["price"] - self.ALLOWANCE) and local.price < (remote["price"] + self.ALLOWANCE):
                    local.exchange_id = remote["id"]
                    local.exchange_timestamp = remote["timestamp"]
                    local.quantity = remote["amount"]
                    local.status = "WORKING"
        
        ### TODO Consider orders that were active but are
        ###      no longer visible, indicating order was FILLED!
        xxx xxx xxx
        
        ### TODO Filter for user-placed orders

        ### TODO Alert if orders are found that do not match
        ###      either the order book or user-placed orders
                    
    def bids(self, order_book):
        for order in order_book.fantasyBids():
            self.trader.place(order)

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
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        print response.body
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

@app.route("/")
def hello():
    trader = CampBX()

    order_book = Orders(trader)
    algo = Algorithm(trader, order_book)
    algo.run()
        
    tick = trader.tick()
    return render_template('index.html', 
        order_book=order_book.order_book,
        bid=tick["bid"], ask=tick["ask"])

if __name__ == "__main__":
    app.debug = True
    app.run()
