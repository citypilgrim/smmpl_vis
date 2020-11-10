# imports
import multiprocessing as mp
import os
import os.path as osp
import pickle

import numpy as np
import pandas as pd

from .arrayvis import arrayvis
from .productmaskvis import productmaskvis
from ..global_imports.smmpl_vis import *
from ..solaris_opcodes.product_calc import main as product_calc


# params
_arraycmap_l = [
    'Blues'
]
_productmaskcmap_l = [
    None
]

_readduration = pd.Timedelta(30, 'm')
_initreaddatatimes = 1

_productarraykey = 'nrb'
_arraytimestampkey = 'Timestamp'

# class
class productvis():

    def __init__(
            self,
            timeobj,

            lidarname, mplreader,
            angularoffset=0,

            datakey_l=[],
            productkey_d={},
    ):
        '''
        This object will control the following sub objects.
        1. arrayvis: plot out the computed data arrays
        2. productmaskvis: plots out the mask for the computed products

        It will also be incharge of grabbing data and passing it onto the other objects
        '''
        self.to = timeobj
        self.starttime = self.to.get_ts()
        self.endtime = self.starttime + _readduration

        self.lidarname = lidarname
        self.mplreader = mplreader
        self.angularoffset = angularoffset

        self.ts_ta = None
        self.data_queue = mp.Queue()
        self.data_d = None
        self.datalastts = None
        self.iter_count = 0
        self.serial_dir = DIRCONFN(
            osp.dirname(osp.dirname(osp.abspath(__file__))),
            TEMPSERIALDIR,
            PRODUCTVISSERIAL,
        )

        # initial data read
        print('initialising productvis data')
        self._queue_data(_initreaddatatimes)
        self._get_data(True)

        # initial obj creation
        self.arrayvis_l = []    # array objects
        for i, datakey in enumerate(datakey_l):
            self.arrayvis_l.append(arrayvis(self, datakey, timeobj, _arraycmap_l[i]))
        self.productmaskvis_l = []    # product mask objects
        for i, (key, value) in enumerate(productkey_d.items()):
            self.productmaskvis_l.append(
                productmaskvis(self, key, value, timeobj, _productmaskcmap_l[i])
            )

        self.obj_l = self.arrayvis_l + self.productmaskvis_l


    def init_vis(self, axl):
        for obj in self.obj_l:
            obj.init_vis(axl)

    def _queue_data(self, n):
        for i in range(n):
            # serialising data and writing to file
            data_d = product_calc(
                self.lidarname, self.mplreader,
                starttime=self.starttime, endtime=self.endtime,
                verbboo=False
            )
            serial_dir = self.serial_dir.format(self.iter_count)
            with open(serial_dir, 'wb') as f:
                print(f'writing productvis serial data to {serial_dir}')
                pickle.dump(data_d, f)
            # message passing
            self.iter_count += 1
            self.data_queue.put(serial_dir)
            # iterating the next time range to consider
            self.starttime += _readduration
            self.endtime += _readduration

    def _get_data(self, init_boo):
        '''
        gets the data from data_queue and initiates a _queue_data if the queue
        size is less than _initreaddatatimes,
        will throw an error if nothing is in the queue
        '''
        # grabbing new data from queue
        serial_dir = self.data_queue.get()
        with open(serial_dir, 'rb') as f:
            self.data_d = pickle.load(f)
        os.remove(serial_dir)   # deleting temp file

        # setting new array data; dependent on outputs of product_calc
        self.array_d = self.data_d[_productarraykey]

        # starting data queue if the data stock is low
        if self.data_queue.qsize() < _initreaddatatimes:
            self._queue_data(_initreaddatatimes)
            # starting multiprocess
            print('starting productvis background data retrieval')
            mp.Process(
                target=self._queue_data,
                args=(_initreaddatatimes, )
            ).start()

        # resetting the indices
        self.ts_ta = self.data_d[_productarraykey][_arraytimestampkey]
        self.datalastts = self.ts_ta[-1]

        # let objects retrieve new data
        if not init_boo:
            for obj in self.obj_l:
                obj.get_data()

    def update_ts(self):
        # updating objects
        for obj in self.obj_l:
            obj.update_ts()

        # grabbing new data and running update timestamp again if the
        # previous data set could not encompass the set
        if self.to.get_ts() >= self.datalastts:
            self._get_data(False)
            self.update_ts()

    def update_toseg(self):
        pass


# testing
if __name__ == '__main__':
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D

    from ..solaris_opcodes.file_readwrite import smmpl_reader
    from ..smmpl_opcodes.scanpat_calc.timeobj import timeobj


    to = timeobj(
        pd.Timestamp('202008040800'),
        pd.Timestamp('202008051100'),
        8,
        pd.Timedelta(1, 'm'),
        pd.Timedelta(30, 'm'),
        None
    )
    pv = productvis(
        to,
        'smmpl_E2', smmpl_reader,
        angularoffset=ANGOFFSET,
        datakey_l=[
            'SNR_tra'
        ]
    )

    # figure creation
    _scale = 1.3
    _curlyl = 30
    fig3d = plt.figure(figsize=(10, 10), constrained_layout=True)
    ax3d = fig3d.add_subplot(111, projection='3d')
    ax3d.pbaspect = [_scale, _scale, _scale]
    ax3d.set_xlabel('South -- North')
    ax3d.set_ylabel('East -- West')
    ax3d.set_xlim([-_curlyl/2, _curlyl/2])
    ax3d.set_ylim([-_curlyl/2, _curlyl/2])
    ax3d.set_zlim([0, _curlyl])

    pv.init_vis([ax3d])

    to.ts = LOCTIMEFN(pd.Timestamp('202008040830'), 8)  # fastforward the time
    pv.update_ts()

    plt.show()
