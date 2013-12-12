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
    def _wait(self):
        while time.time() < self.timestamp:
            time.sleep(0.1)
    def _timestamp(self):
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
            self._wait()
            response = unirest.post(url, headers=self.headers, params={})
            self._timestamp()
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
        self._wait()
        response = unirest.post(url, headers=self.headers, params={})
        self._timestamp()
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        if not "Success" in response.body:
            print response.body
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
        self._wait()
        response = unirest.post("http://campbx.com/api/xticker.php") #, self.headers, {})
        self._timestamp()
        return { 'bid': float(response.body["Best Bid"]), 'ask': float(response.body["Best Ask"]) }

    def orders(self):
        url = "https://campbx.com/api/myorders.php?user=%s&pass=%s" % (self.login, self.password)
        self._wait()
        response = unirest.post(url, headers=self.headers, params={})
        self._timestamp()
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
        self._wait()
        response = unirest.post(url, headers=self.headers, params={})
        self._timestamp()
        if "Error" in response.body:
            raise Exception("Bitcoin exchange API error: %s" % response.body["Error"])
        return { "usd-liquid": response.body["Liquid USD"],
                 "usd-total":  response.body["Total USD"],
                 "btc-liquid": response.body["Liquid BTC"],
                 "btc-total":  response.body["Total BTC"] }

