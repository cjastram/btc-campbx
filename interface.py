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

import unirest
from flask import Flask
from flask import render_template
app = Flask(__name__)

class CampBX:
    login = "X"
    password = "X"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json; charset=UTF-8'
    }
    def tick(self):
        response = unirest.post("http://campbx.com/api/xticker.php", self.headers, {})
        return { 'bid': float(response.body["Best Bid"]), 'ask': float(response.body["Best Ask"]) }
    def buy(self, qty, price):
        params = {
            'user': self.login,
            'pass': self.password,
            'TradeMode': 'QuickBuy',
            'Quantity': qty,
            'Price': price
        }
        url = "https://CampBX.com/api/tradeenter.php"
        response = unirest.post(url, self.headers, params)
        if "Error" in response.body:
            raise Exception(response.body["Error"])
        print response.body

@app.route("/")
def hello():
    trader = CampBX()
    tick = trader.tick()

    floor = 150
    ceiling = tick["ask"]
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
    print trader.buy("0.01", "147")
    print ideal_pairs

    return render_template('index.html', bid=tick["bid"], ask=tick["ask"])

if __name__ == "__main__":
    app.debug = True
    app.run()
