from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

class Link(BaseModel):
    model_config = ConfigDict(extra='allow')
    href: str
    type: Optional[str] = None
    rel: Optional[Union[str, List[str]]] = None
    title: Optional[str] = None
    templated: Optional[bool] = False
    properties: Optional[Dict[str, Any]] = None

class Contributor(BaseModel):
    model_config = ConfigDict(extra='allow')
    name: str
    sortAs: Optional[str] = None
    role: Optional[str] = None

class Metadata(BaseModel):
    model_config = ConfigDict(extra='allow')
    title: str
    subtitle: Optional[str] = None
    identifier: Optional[str] = None
    author: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    translator: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    editor: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    artist: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    illustrator: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    letterer: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    penciler: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    colorist: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    inker: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    contributor: Optional[Union[str, List[Union[str, Contributor]], Contributor]] = None
    description: Optional[str] = None
    publisher: Optional[Union[str, Contributor, List[Union[str, Contributor]]]] = None
    published: Optional[str] = None
    subject: Optional[Union[str, List[Union[str, Dict[str, Any]]]]] = None
    language: Optional[Union[str, List[str]]] = None
    modified: Optional[str] = None
    conformsTo: Optional[Union[str, List[str]]] = None
    belongsTo: Optional[Dict[str, Any]] = None

class Publication(BaseModel):
    model_config = ConfigDict(extra='allow')
    metadata: Metadata
    links: List[Link]
    images: Optional[List[Link]] = None
    readingOrder: Optional[List[Link]] = None
    resources: Optional[List[Link]] = None
    belongsTo: Optional[Dict[str, Any]] = None

class Group(BaseModel):
    model_config = ConfigDict(extra='allow')
    metadata: Metadata
    links: Optional[List[Link]] = None
    publications: Optional[List[Publication]] = None
    navigation: Optional[List[Link]] = None

class OPDSFeed(BaseModel):
    model_config = ConfigDict(extra='allow')
    metadata: Metadata
    links: List[Link]
    publications: Optional[List[Publication]] = None
    navigation: Optional[List[Link]] = None
    groups: Optional[List[Group]] = None
    facets: Optional[List[Dict[str, Any]]] = None
