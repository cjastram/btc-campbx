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

import math
import unirest
from flask import Flask
from flask import render_template
app = Flask(__name__)


class Orders(list):
    order_book_filename = "order-book.yaml"
    order_book = []

    def __init__(self):
        orders.readOrderBook()
        filled = orders.mapExchangeOrders(self.getOrders())

    def readOrderBook(self):
        self.order_book = []
        try:
            f = file(self.order_book_filename, "r")
            self.order_book = yaml.load(f)
            f.close()
        except IOError:
            print "--> Failed to load order book, starting anew"

    def mapExchangeOrders(self, orders):
        recorded = []
        for local in self.order_book:
            bid_exchange_id = local["bid"]["exchange_id"]
            ask_exchange_id = local["ask"]["exchange_id"]
            if bid_exchange_id or ask_exchange_id:
                if bid_exchange_id: recorded.append(bid_exchange_id)
                if ask_exchange_id: recorded.append(ask_exchange_id)

        # If recorded and active, order is working
        # If recorded but not active, order was filled
        # If active but not recorded, order is probably a user order, should ignore
        # If neither active nor recorded, WTF?

        active = [remote["id"] for remote in orders]
        working = [id for id in active if id in recorded]
        filled = [id for id in recorded if id not in active]
        user = [id for id in active if id not in recorded]
        wtf = [id for id in active if id not in working and id not in filled]
        for id in user:
            print "--> User order: %s" % id
        for id in wtf:
            print "--> UNKNOWN ORDER: %s" % id

        #print "RECORDED"
        #print recorded
        #print "ACTIVE"
        #print active
        #print "ALL"
        #print all
        #print "WORKING"
        #print working
        #print "FILLED"
        #print filled
        #print "USER"
        #print user
        #print "DUDE"
        #print wtf

        ### Reset statuses
        for local in self.order_book:
            for side in ["bid", "ask"]:
                id = local[side]["exchange_id"]
                local[side]["status"] = None
                if id in working: local[side]["status"] = "WORKING"
                if id in filled: local[side]["status"] = "FILLED"
    
    def filledBidsUnpaired(self):
        filled = []
        for local in self.order_book:
            if local["bid"]["status"] == "FILLED" and local["ask"]["exchange_id"] is None:
                filled.append(local["bid"]["exchange_id"])
        return filled
    
    def details(self, id):
        for local in self.order_book:
            for side in ["bid", "ask"]:
                if local[side]["exchange_id"] == id:
                    return local[side]

    def bids(self):
        pass
    def asks(self):
        pass
    def add(self, side, amount, price, exchange_id, exchange_timestamp):
        self.append({"side": side,
                     "price": price,
                     "amount": amount,
                     "exchange_id": exchange_id,
                     "exchange_timestamp": exchange_timestamp,
                     })

class Algorithm:
    trader = None
    
    def __init__(self, trader):
        self.trader = trader

    def run(self):
        orders = Orders()
    
        ### Clear order pairs
        for local in orders.order_book:
            if local["bid"]["status"] == "FILLED" and local["ask"]["status"] == "FILLED":
                print "--> UNIMPLEMENTED: need to clear order!"

        ### Place asks for filled bids
        for id in orders.filledBidsUnpaired():
            print "--> Need to place ask orders for %s" % id

        ### Place new bids

        ### Cancel low orders

        ### Adjust existing orders
        

        print orders
        # {u'Success': u'1921853'}

class CampBX:
    login = "X"
    password = "X"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json; charset=UTF-8'
    }
    def tick(self):
        response = unirest.post("http://campbx.com/api/xticker.php") #, self.headers, {})
        return { 'bid': float(response.body["Best Bid"]), 'ask': float(response.body["Best Ask"]) }
    def bid(self, qty, price):
        params = {
            'user': self.login,
            'pass': self.password,
            'TradeMode': 'QuickBuy',
            'Quantity': qty,
            'Price': price
        }
        url = "https://campbx.com/api/tradeenter.php"
        #args = ""
        #for key, value in params.iteritems():
            #if len(args): args = args + "&"
            #args = args + "%s=%s" % (key, value)
        #url = url + "?" + args
        #response = unirest.post(url, headers=self.headers, params={})
        #if "Error" in response.body:
            #raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        # {u'Success': u'1921853'}
        print response.body

    def getOrders(self):
        url = "https://campbx.com/api/myorders.php?user=%s&pass=%s" % (self.login, self.password)
        response = unirest.post(url, headers=self.headers, params={})
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
                    "price": exchange_order["Price"],
                    "amount": exchange_order["Quantity"],
                    "timestamp": exchange_order["Order Entered"],
                    })
        return orders
        

@app.route("/")
def hello():
    trader = CampBX()

    tick = trader.tick()
    ceiling = tick["ask"]
    floor = math.floor(ceiling * 0.80)
    interval = 5
    spread = 7
    ideal_pairs = []

    # No continuous variable, need to line up
    # the order grid in a predictable way.
    floor = floor - (floor % 7)

    bid = floor
    while bid < ceiling:
        pair = { 
            "bid": bid,
            "ask": (bid+spread)
        }
        ideal_pairs.append(pair)
        bid = bid + interval
    #print trader.buy("0.01", "147")
    #print ideal_pairs

    algo = Algorithm(trader)
    print algo.run()

    return render_template('index.html', bid=tick["bid"], ask=tick["ask"])

if __name__ == "__main__":
    app.debug = True
    app.run()
