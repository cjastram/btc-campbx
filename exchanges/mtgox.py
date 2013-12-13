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

import base64
import hashlib
import hmac
import math
import unirest
import time
import urllib, urllib2
from hmac import HMAC
        
import pprint
pp = pprint.PrettyPrinter(indent="2")

class MtGox:
    timestamp = None
    settings = None
    base = "https://data.mtgox.com/api/2/"
    #headers = {
        #'Accept': 'application/json',
        #'Content-Type': 'application/json; charset=UTF-8'
    #}

    def __init__(self, settings=None):
        self._timestamp()
        self.settings = settings

    def _wait(self):
        while time.time() < self.timestamp:
            time.sleep(0.01)
    def _timestamp(self):
        self.timestamp = int(math.ceil(time.time())) + 1
    def _authParams(self, path, params):
        params = dict(params)
        params['nonce'] = str(int(time.time()*1e5))
        data = urllib.urlencode(params)

        base = 'https://data.mtgox.com/api/2/'
        secret = base64.b64decode(self.settings.auth("mtgox_secret"))
        key = self.settings.auth("mtgox_key")
        
        ### Only v2 of MtGox API has path and ASCII NULL
        message = path + chr(0) + data
        hmac_obj = hmac.new(secret, message, hashlib.sha512)
        hmac_sign = base64.b64encode(hmac_obj.digest())

        header = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'gox2 based client',
            'Rest-Key': key,
            'Rest-Sign': hmac_sign,
        }
        return (data, header)
        
    def cancel(self, order):
        return
        print "--> Cancelling order"
        print order
        if order.status == "FANTASY":
            order.status = "CANCELLED"
        else:
            url = "https://www.bitstamp.net/api/cancel_order/"

            params = self._authParams()
            params["id"] = order.exchange_id
            self._wait()
            response = unirest.post(url, params=params)
            self._timestamp()

            if response.body == "true":
                order.status = "CANCELLED"
            else:
                print "--> FAILED TO CANCEL ORDER! response.body => "
                print response.body
    
    def place(self, order):
        return
        print "--> Placing %s for %f at %f" % (order.side, order.quantity, order.price)

        appendix = None
        if order.side == "bid": appendix = "buy"
        elif order.side == "ask": appendix = "sell"
        else: raise Exception("oops")
        url = "https://www.bitstamp.net/api/%s/" % appendix

        params = self._authParams()
        params.update({"amount": order.quantity, "price": order.price})

        self._wait()
        response = unirest.post(url, params=params)
        self._timestamp()

        if "error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["error"]["__all__"])
        if not "id" in response.body:
            print response.body
            raise Exception("Bitcoin exchange API failed to return order success!")

        order.exchange_id = response.body["id"]
        order.price = response.body["price"]
        order.amount = response.body["amount"]
        order.status = "WORKING"

    def tick(self):
        path = "BTCUSD/money/ticker_fast"
        data, headers = self._authParams(path, {})
        url = self.base + path
        response = unirest.get(url, headers=headers)
        return { 'bid': float(response.body["data"]["buy"]["value"]), 'ask': float(response.body["data"]["sell"]["value"]) }

    def orders(self):
        return
        url = "https://www.bitstamp.net/api/open_orders/"
        self._wait()
        response = unirest.post(url, params=self._authParams())
        self._timestamp()
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        
        orders = []
        for exchange_order in response.body:
            order_types = ["bid", "ask"]
            order_type = order_types[exchange_order["type"]]
            orders.append({
                "id": exchange_order["id"],
                "side": order_type,
                "price": float(exchange_order["price"]),
                "amount": float(exchange_order["amount"]),
                "timestamp": exchange_order["datetime"],
                })
        return orders

    def balances(self):
        path = "BTCUSD/money/info"
        data, headers = self._authParams(path, {})
        url = self.base + path
        response = unirest.post(url, headers=headers, params=data)
        r = response.body["data"]
        return { "usd-liquid": float(r["Wallets"]["USD"]["Balance"]["value"]) - float(r["Wallets"]["USD"]["Open_Orders"]["value"]),
                 "usd-total": float(r["Wallets"]["USD"]["Balance"]["value"]),
                 "btc-liquid": float(r["Wallets"]["BTC"]["Balance"]["value"]) - float(r["Wallets"]["BTC"]["Open_Orders"]["value"]),
                 "btc-total": float(r["Wallets"]["BTC"]["Balance"]["value"]),
               }

