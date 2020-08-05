"""
*******************************************************
 * Copyright (C) 2017 MindsDB Inc. <copyright@mindsdb.com>
 *
 * This file is part of MindsDB Server.
 *
 * MindsDB Server can not be copied and/or distributed without the express
 * permission of MindsDB Inc
 *******************************************************
"""

import struct
import math

# import logging
from mindsdb.api.mysql.mysql_proxy.data_types.mysql_packet import Packet
from mindsdb.api.mysql.mysql_proxy.data_types.mysql_datum import Datum
from mindsdb.api.mysql.mysql_proxy.libs.constants.mysql import COMMANDS, getConstName, TYPES


class CommandPacket(Packet):
    '''
    Implementation based on description:
    https://mariadb.com/kb/en/library/1-connecting-connecting/#initial-handshake-packet
    '''

    def _read_byte(self, buffer):
        b = buffer[:1]
        buffer = buffer[1:]
        b = struct.unpack('<B', b)[0]
        return b, buffer

    def setup(self, length=0, count_header=1, body=''):
        if length == 0:
            return

        # self.salt=self.session.salt

        self._length = length
        self._seq = count_header
        self._body = body

        self.type = Datum('int<1>')
        buffer = body
        buffer = self.type.setFromBuff(buffer)

        if self.type.value in (COMMANDS.COM_QUERY, COMMANDS.COM_STMT_PREPARE):
            self.sql = Datum('str<EOF>')
            buffer = self.sql.setFromBuff(buffer)
        elif self.type.value == COMMANDS.COM_STMT_EXECUTE:
            # https://mariadb.com/kb/en/com_stmt_execute/
            self.stmt_id = Datum('int<4>')
            buffer = self.stmt_id.setFromBuff(buffer)
            self.flags = Datum('int<1>')
            buffer = self.flags.setFromBuff(buffer)
            self.iteration_count = Datum('int<4>')
            buffer = self.iteration_count.setFromBuff(buffer)

            self.parameters = []

            statement = self.session.statements[self.stmt_id.value]
            if statement['type'] == 'insert':
                num_params = statement['num_params']
                if num_params > 0:
                    # read null-map
                    null_bytes = math.floor((num_params + 7) / 8)
                    nulls = []
                    for i in range(null_bytes):
                        b, buffer = self._read_byte(buffer)
                        for i in range(7, -1, -1):
                            nulls.append(((1 << i) & b) != 0)

                    # read send-type byte
                    b, buffer = self._read_byte(buffer)

                    types = []
                    if b == 1:
                        # read types
                        for i in range(num_params):
                            t, buffer = self._read_byte(buffer)
                            s, buffer = self._read_byte(buffer)
                            types.append(dict(
                                type=t,
                                signed=s
                            ))

                    self.parameters = []
                    for i in range(num_params):
                        if nulls[i]:
                            self.parameters.append(None)
                            continue
                        if types[i]['type'] in (TYPES.MYSQL_TYPE_VAR_STRING, TYPES.MYSQL_TYPE_STRING):
                            x = Datum('string<lenenc>')
                            buffer = x.setFromBuff(buffer)
                            self.parameters.append(x.value.decode())
                        else:
                            pass
                        # TODO other fields

        elif self.type.value == COMMANDS.COM_STMT_CLOSE:
            self.stmt_id = Datum('int<4>')
            buffer = self.stmt_id.setFromBuff(buffer)
        elif self.type.value == COMMANDS.COM_STMT_FETCH:
            self.stmt_id = Datum('int<4>')
            buffer = self.stmt_id.setFromBuff(buffer)
            self.limit = Datum('int<4>')
            buffer = self.limit.setFromBuff(buffer)
        else:
            self.data = Datum('str<EOF>')
            buffer = self.data.setFromBuff(buffer)

    def __str__(self):
        return str({
            'header': {'length': self.length, 'seq': self.seq},
            'type': getConstName(COMMANDS, self.type.value),
            'vars': self.__dict__
        })
