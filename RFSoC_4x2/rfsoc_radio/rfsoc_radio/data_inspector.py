__author__ = "David Northcote"
__organisation__ = "The Univeristy of Strathclyde"
__support__ = "https://github.com/strath-sdr/rfsoc_radio"

from pynq import DefaultIP
from pynq import DefaultHierarchy
from pynq import allocate
import numpy as np
import math
import ipywidgets as ipw
from .sdr_plots import TimePlot, ConstellationPlot, SpectrumAnalyser
from .dma_timer import DmaTimer


class DataInspector(DefaultHierarchy):
    
    def __init__(self, description, plotting_rate = 0.5, autoscale = False):
        super().__init__(description)
        
        self.fractional = 14
        self.data_inspector_module.packetsize = 64
        self.data_inspector_module.enable = 0
        self.data_inspector_module.reset = 1
        
        self._autoscale = autoscale
        self._plotting_rate = plotting_rate
        self.buffer = allocate(shape=(int(self.data_inspector_module.packetsize*2),), dtype=np.int16)
        
        self._data = self.get_frame()
        self._t_plot = TimePlot(self._data, animation_period=0)
        self._c_plot = ConstellationPlot(self._data, animation_period=0)
        self._f_plot = SpectrumAnalyser(self._data, fs=100e3, animation_period=0)
        self._plot_controller = DmaTimer(self._update_data, self.get_frame, self._plotting_rate)
        
    def set_axisrange(self, axisrange):
        self._t_plot.set_axisrange(axisrange)
        self._c_plot.set_axisrange(axisrange)
        
    def set_frequency(self, fs):
        self._f_plot.set_frequency(fs)
        self._t_plot.sample_frequency = fs
        
    def set_plotting_rate(self, rate):
        self._plotting_rate = rate
        self._plot_controller.t = rate
        
    def set_shape(self, shape):
        """Set the buffer shape by first freeing the existing buffer
        and then allocating a new buffer with the given tuple. Obtain the
        tuple product to set the packetsize of the data_inspector_module.
        """
        self.buffer.freebuffer()
        lshape = list(shape)
        lshape[0] = lshape[0] * 2
        tshape = tuple(lshape)
        self.buffer = allocate(shape=tshape, dtype=np.int16)       
        product = 1 
        for i in shape:  
            product *= i
        self.data_inspector_module.packetsize = product
        
    def get_frame(self):
        """Get a single buffer of time data from the logic fabric
        """
        self.data_inspector_module.reset = 0
        self.axi_dma.recvchannel.transfer(self.buffer)
        self.data_inspector_module.enable = 1
        self.axi_dma.recvchannel.wait()
        self.data_inspector_module.enable = 0
        self.data_inspector_module.reset = 1
        t_data = np.array(self.buffer) * 2**-self.fractional
        c_data = t_data[::2] + 1j * t_data[1::2]
        if self._autoscale:
            return self._scale_data(c_data)
        else:
            return c_data
    
    def _update_data(self, data):
        """Update the timer and constellation plots with new data"""
        self._data = data
        self._t_plot.update_data(data)
        self._c_plot.update_data(data)
        self._f_plot.update_data(data)
        
    def _scale_data(self, data):
        median = np.max(data)
        mag = abs(median)
        scale = 1/mag
        return data * scale
    
    def spectrum_plot(self):
        return self._f_plot.get_widget()
    
    def time_plot(self):
        """Returns a time plot of inspected data
        """
        return self._t_plot.get_widget()
    
    def constellation_plot(self):
        """Returns a constellation plot of inspected data
        """
        return self._c_plot.get_widget()
    
    def plot_control(self):
        """Return the plot controller
        """
        return self._plot_controller.get_widget()
    
    def visualise(self):
        """Return all the available features of the data inspector module"""
        return ipw.VBox([ipw.HBox([self.time_plot(), self.constellation_plot()]), self.plot_control(), self.spectrum_plot()])
    
    @staticmethod
    def checkhierarchy(description):
        if 'axi_dma' in description['ip'] \
           and 'data_inspector_module' in description['ip']:
            return True
        return False 
        
class DataInspectorCore(DefaultIP):
    """Driver for Data Inspector's core logic IP
    Exposes all the configuration registers by name via data-driven properties
    """

    def __init__(self, description):
        super().__init__(description=description)

    bindto = ['UoS:RFSoC:inspector:1.0']

# LUT of property addresses for our data-driven properties
_dataInspector_props = [("reset", 0),
                        ("enable", 4),
                        ("packetsize", 8)]

# Function to return a MMIO Getter and Setter based on a relative address
def _create_mmio_property(addr):
    def _get(self):
        return self.read(addr)

    def _set(self, value):
        self.write(addr, value)

    return property(_get, _set)

# Generate getters and setters based on _dataInspector_props
for (name, addr) in _dataInspector_props:
    setattr(DataInspectorCore, name, _create_mmio_property(addr))
    