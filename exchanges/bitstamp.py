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
import math
import unirest
import time

class BitStamp:
    timestamp = None
    settings = None
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
    def _authParams(self):
        nonce = self.timestamp # Forced unique by _wait()
        api_key = self.settings.auth("api_key")
        api_secret = self.settings.auth("api_secret")
        client_id = self.settings.auth("client_id")
        message = "%i%s%s" % (nonce, client_id, api_key)
        signature = hmac.new(api_secret, msg=message, digestmod=hashlib.sha256).hexdigest().upper()
        return { "key": api_key, "signature": signature, "nonce": nonce }
        
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
        self._wait()
        response = unirest.get("https://www.bitstamp.net/api/ticker/") #, self.headers, {})
        self._timestamp()
        return { 'bid': float(response.body["bid"]), 'ask': float(response.body["ask"]) }

    def orders(self):
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
        url = "https://www.bitstamp.net/api/balance/"
        self._wait()
        response = unirest.post(url, params=self._authParams())
        self._timestamp()
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        return { "usd-liquid": response.body["usd_available"],
                 "usd-total":  response.body["usd_balance"],
                 "btc-liquid": response.body["btc_available"],
                 "btc-total":  response.body["btc_balance"] }

