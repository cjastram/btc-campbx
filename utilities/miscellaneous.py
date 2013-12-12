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

import yaml

class Log:
    def __init__(self):
        print "--> Initializing log..."

class Settings:
    _filename = "settings.yaml"
    def _read(self):
        f = open(self._filename, 'r')
        temp = yaml.safe_load(f)
        f.close()
        return temp
    def algorithm(self, key, value=None):
        d = self._read()
        return d["algorithm"][key]
    def auth(self, key, value=None):
        d = self._read()
        return d["auth"][key]
    def group(self, key):
        d = self._read()
        return d[key]
        
