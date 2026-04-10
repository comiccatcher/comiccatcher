from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_validator, model_validator

class Link(BaseModel):
    model_config = ConfigDict(extra='allow')
    href: Optional[str] = None
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
    links: Optional[List[Link]] = None

class Collection(BaseModel):
    model_config = ConfigDict(extra='allow')
    name: str
    sortAs: Optional[str] = None
    identifier: Optional[str] = None
    position: Optional[Union[float, str]] = None
    numberOfItems: Optional[int] = None
    links: Optional[List[Link]] = None

class BelongsTo(BaseModel):
    model_config = ConfigDict(extra='allow')
    series: Optional[List[Collection]] = None
    collection: Optional[List[Collection]] = None

    @model_validator(mode='before')
    @classmethod
    def standardize(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"series": [{"name": data}]}
        if not isinstance(data, dict):
            return data
            
        new_data = data.copy()
        for key in ["series", "collection"]:
            val = data.get(key)
            if val:
                if not isinstance(val, list):
                    val = [val]
                
                standard_list = []
                for item in val:
                    if isinstance(item, str):
                        standard_list.append({"name": item})
                    else:
                        standard_list.append(item)
                new_data[key] = standard_list
        return new_data

class Presentation(BaseModel):
    model_config = ConfigDict(extra='allow')
    layout: Optional[str] = None # fixed, reflowable
    orientation: Optional[str] = None # landscape, portrait, auto
    spread: Optional[str] = None # auto, landscape, both, none
    clipped: Optional[bool] = None
    fit: Optional[str] = None # contain, cover, width, height

class Metadata(BaseModel):
    model_config = ConfigDict(extra='allow')
    title: Optional[str] = None
    subtitle: Optional[str] = None
    identifier: Optional[str] = None
    
    # Contributor roles standardized to List[Contributor] via validator
    author: Optional[List[Contributor]] = None
    translator: Optional[List[Contributor]] = None
    editor: Optional[List[Contributor]] = None
    artist: Optional[List[Contributor]] = None
    illustrator: Optional[List[Contributor]] = None
    letterer: Optional[List[Contributor]] = None
    penciler: Optional[List[Contributor]] = None
    colorist: Optional[List[Contributor]] = None
    inker: Optional[List[Contributor]] = None
    contributor: Optional[List[Contributor]] = None
    publisher: Optional[List[Contributor]] = None
    imprint: Optional[List[Contributor]] = None
    
    description: Optional[str] = None
    published: Optional[str] = None
    subject: Optional[Union[str, List[Union[str, Dict[str, Any]]]]] = None
    language: Optional[Union[str, List[str]]] = None
    modified: Optional[str] = None
    conformsTo: Optional[Union[str, List[str]]] = None
    numberOfBytes: Optional[int] = None
    
    belongsTo: Optional[BelongsTo] = None
    presentation: Optional[Presentation] = None
    
    numberOfItems: Optional[int] = None
    itemsPerPage: Optional[int] = None
    currentPage: Optional[int] = None
    numberOfPages: Optional[int] = None

    @field_validator("author", "translator", "editor", "artist", "illustrator", "letterer", 
                     "penciler", "colorist", "inker", "contributor", "publisher", "imprint", 
                     mode='before')
    @classmethod
    def standardize_contributors(cls, v):
        if v is None:
            return None
        if not isinstance(v, list):
            v = [v]
        
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(Contributor(name=item))
            elif isinstance(item, dict):
                if "name" in item:
                    result.append(Contributor(**item))
                else:
                    # Fallback for dicts missing 'name'
                    result.append(Contributor(name=str(item.get("title") or item.get("label") or item)))
            elif isinstance(item, Contributor):
                result.append(item)
            else:
                result.append(Contributor(name=str(item)))
        return result

class Publication(BaseModel):
    model_config = ConfigDict(extra='allow')
    metadata: Optional[Metadata] = None
    links: Optional[List[Link]] = None
    images: Optional[List[Link]] = None
    readingOrder: Optional[List[Link]] = None
    resources: Optional[List[Link]] = None
    actions: Optional[List[Link]] = None
    belongsTo: Optional[BelongsTo] = None

    @property
    def is_divina(self) -> bool:
        """Determines if this is an image-based comic/manga manifest."""
        # 1. Check conformsTo for Divina profile
        if self.metadata and self.metadata.conformsTo:
            conforms = self.metadata.conformsTo
            if isinstance(conforms, str):
                if "divina" in conforms: return True
            elif isinstance(conforms, list):
                if any("divina" in str(c) for r in conforms for c in ([r] if not isinstance(r, list) else r)): 
                    # Note: pydantic Union/List nesting can be complex, keeping it simple
                    if any("divina" in str(c) for c in conforms): return True

        # 2. Heuristic: Check if readingOrder contains images
        if self.readingOrder and len(self.readingOrder) > 0:
            first_item = self.readingOrder[0]
            # Handle both Link object and dict (if it hasn't been parsed yet)
            first_type = getattr(first_item, "type", None) or (first_item.get("type") if isinstance(first_item, dict) else "")
            if first_type and "image/" in str(first_type).lower():
                return True
                
        return False

    @property
    def identifier(self) -> str:
        # Check top-level id first, then metadata.identifier
        raw_id = getattr(self, 'id', None)
        if raw_id:
            return str(raw_id)
        if self.metadata and self.metadata.identifier:
            return str(self.metadata.identifier)
        return ""

class Group(BaseModel):
    model_config = ConfigDict(extra='allow')
    metadata: Metadata
    links: Optional[List[Link]] = None
    publications: Optional[List[Publication]] = None
    navigation: Optional[List[Link]] = None

class OPDSFeed(BaseModel):
    model_config = ConfigDict(extra='allow')
    metadata: Optional[Metadata] = None
    links: List[Link]
    publications: Optional[List[Publication]] = None
    navigation: Optional[List[Link]] = None
    groups: Optional[List[Group]] = None
    facets: Optional[List[Union[Group, Dict[str, Any]]]] = None
    authentication: Optional[List[Dict[str, Any]]] = None
