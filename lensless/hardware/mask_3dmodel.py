import cadquery as cq
import numpy as np
from typing import Union
from abc import ABC, abstractmethod

from lensless.hardware.mask import Mask

class Frame(ABC):
  @abstractmethod
  def generate(self, mask_size, depth: float) -> cq.Workplane:
    pass

class Connection(ABC):
  @abstractmethod
  def generate(self, mask:np.ndarray, mask_size, depth: float) -> cq.Workplane:
    """connections can in general use the mask array to determine where to connect to the mask, but it is not required."""
    pass

class MaskModel():
  def __init__(self,
    mask_array: np.ndarray,
    frame: Frame,
    connection: Connection, 
    mask_size: Union[tuple[float, float], np.ndarray],
    depth: float,
    simplify: bool = False,
    show_axis: bool = False,
  ):
    """_summary_

    Args:
        mask_array (np.ndarray): Array of the mask to generate from. 1 is opaque, 0 is transparent.
        frame (Frame): Frame object defining the frame around the mask.
        connection (Connection): Connection object defining how to connect the frame to the mask.
        mask_size (Union[tuple[float, float], np.ndarray]): dimensions of the mask in meters.
        depth (float): How thick to make the mask in millimeters.
        simplify (bool, optional): Combines all objects in the model to a single object. Results in a much smaller 3d model file and faster post processing. But takes a considerable amount of more time to generate model. Defaults to False.
        show_axis (bool, optional): Show axis for debug purposes. Defaults to False.
    """
    
    self.mask = mask_array
    self.frame: Frame = frame
    self.connections: Connection = connection
    
    if isinstance(mask_size, tuple):
      self.mask_size = np.array(mask_size)*1e3
    else:
      self.mask_size = mask_size*1e3
      
    self.depth = depth
    self.simplify = simplify
    self.show_axis = show_axis
      
    self._generate_3d_model()
    
  @classmethod
  def from_mask(cls, mask: Mask, frame: Frame, connection: Connection, **kwargs):
    return cls(
      mask_array = mask.mask, 
      frame = frame, 
      connection = connection,
      mask_size = mask.sensor_size,
      **kwargs
    )
    
  def mask_to_points(mask:np.ndarray, mask_size: Union[tuple[float, float], np.ndarray], px_size: Union[tuple[float, float], np.ndarray]):
    """turns mask into 2D point coordinates"""
    indices = np.argwhere(mask == 0) - np.array(mask.shape)/2
    coordinates = indices*px_size
    return coordinates
  
  def _generate_3d_model(self):
    """based on provided mask, frame and connection between frame and mask, generate a 3d model."""
    frame_model = self.frame.generate(self.mask_size, self.depth)
    connection_model = self.connections.generate(self.mask, self.mask_size, self.depth)
    
    px_size = self.mask_size / self.mask.shape
    points = MaskModel.mask_to_points(self.mask, self.mask_size, px_size)
    mask_model = (cq.Workplane("XY")
      .pushPoints(points)
      .box(px_size[0], px_size[1], self.depth, centered=False, combine=False)
    )
    
    if self.simplify:
      mask_model = mask_model.combine(glue=True)
    
    self.model = cq.Workplane("XY").add(frame_model).add(connection_model).add(mask_model)
    
    if self.show_axis:
      axis_thickness = 0.1
      axis_length = 20
      axis_test = (cq.Workplane("XY")
        .box(axis_thickness, axis_thickness, axis_length)
        .box(axis_thickness, axis_length, axis_thickness)
        .box(axis_length, axis_thickness, axis_thickness)
      )
      self.model = self.model.add(axis_test)
    
    if self.simplify:
      self.model = self.model.combine(glue=False)
    
  def save(self, fname):
    assert self.model is not None
    cq.exporters.export(self.model, fname)
    
    
# from here, implementations of frames and connections

class SimpleFrame(Frame):
  def __init__(self, padding: float = 2):
    self.padding = padding
    
  def generate(self, mask_size, depth: float) -> cq.Workplane:
    width, height = mask_size[0], mask_size[1]
    return (cq.Workplane("XY")
      .box(width+2*self.padding, height+2*self.padding, depth, centered=(True, True, False))
      .rect(width, height)
      .cutThruAll()
    )

class CrossConnection(Connection):
  """Transverse cross connection"""
  def __init__(self, thickness: float = 0.1, mask_radius: float = None):
    self.thickness = thickness
    self.mask_radius = mask_radius
    
  def generate(self, mask:np.ndarray, mask_size, depth: float) -> cq.Workplane:
    width, height = mask_size[0], mask_size[1]
    model = (cq.Workplane("XY")
      .box(self.thickness, height, depth, centered=(True, True, False))
      .box(width, self.thickness, depth, centered=(True, True, True))
    )
    
    if self.mask_radius is not None:
      circle = cq.Workplane("XY").cylinder(depth, self.mask_radius, centered=(True, True, False))
      model = model.cut(circle)
      
    return model

class SaltireConnection(Connection):
  """Diagonal cross connection"""
  def __init__(self, thickness: float = 0.1, mask_radius: float = None):
    self.thickness = thickness
    self.mask_radius = mask_radius
    
  def generate(self, mask: np.ndarray, mask_size, depth: float) -> cq.Workplane:
    width, height = mask_size[0], mask_size[1]
    width2, height2 = width/2, height/2
    l = self.thickness/np.sqrt(2)
    model = (cq.Workplane("XY")
      .moveTo(- (width2 - l), -height2)
      .lineTo(-width2, -height2)
      .lineTo(-width2, - (height2 - l))
      
      .lineTo(width2 - l, height2)
      .lineTo(width2, height2)
      .lineTo(width2, height2 - l)
      
      .close()
      .extrude(depth)
      
      .moveTo(- (width2 - l), height2)
      .lineTo(-width2, height2)
      .lineTo(-width2, height2 - l)
      
      .lineTo(width2 - l, -height2)
      .lineTo(width2, -height2)
      .lineTo(width2, - (height2 - l))
      
      .close()
      .extrude(depth)
    )
    
    if self.mask_radius is not None:
      circle = cq.Workplane("XY").cylinder(depth, self.mask_radius, centered=(True, True, False))
      model = model.cut(circle)
      
    return model