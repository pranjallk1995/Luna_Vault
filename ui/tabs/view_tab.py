"""View Images tab: the searchable visible-image gallery."""

from images import ImageCollection
from tabs.actions import GalleryActions
from tabs.gallery import ImageGallery
from tabs.shared import SearchFilter, VisiaTab


class ViewTab(VisiaTab):
    def render(self) -> None:
        collection = SearchFilter(
            self.layout,
            key="view_name_search",
            label="Search by image name",
            no_match_message="No filenames or tags match your search.",
        ).apply(ImageCollection.visible(self.api, self.files))
        if collection is not None:
            ImageGallery(self.context, GalleryActions(self.api)).render(collection)
