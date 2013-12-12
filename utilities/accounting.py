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
import yaml

# This helps prevent circular references when we change an order
# and wish to subsequently save the order book.
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
      
        ### Save any changes immediately, in case of crash
        if ORDER_BOOK:
            ORDER_BOOK.saveOrderBook()
    
    def __getattr__(self, key): 
        return self[key]
    def __setattr__(self, key, value): 
        self[key] = value

class Orders(list):
    trader = None
    settings = None

    order_book_filename = "order-book.yaml"

    def __init__(self, trader, settings):
        global ORDER_BOOK
        self.trader = trader
        self.settings = settings
        self.readOrderBook()
        ORDER_BOOK = self

    def readOrderBook(self):
        del self[0:len(self)]
        try:
            f = file(self.order_book_filename, "r")
            loaded = yaml.load(f)
            for block in loaded:
                self.add(block)
            f.close()
        except IOError:
            print "--> Failed to load order book, starting anew"

    def saveOrderBook(self):
        f = file(self.order_book_filename, "w")
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
        allowance = self.settings.algorithm("allowance")
        bids = []
        for order in self:
            if order.side == "bid" and order.status != "CANCELLED":
                if order.price > (price - allowance) and order.price < (price + allowance):
                    bids.append(order)
        return bids
    
    def bidsUnderPrice(self, price):
        return [order for order in self if order.side == "bid" and order.price < price]
    
    def fantasies(self):
        return [order for order in self if order.status == "FANTASY"]
    
    def fantasyBids(self):
        return [order for order in self if order.status == "FANTASY" and order.side == "bid"]
    
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

