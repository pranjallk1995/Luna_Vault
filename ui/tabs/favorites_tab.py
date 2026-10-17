"""Favorites tab: the View Images gallery limited to favorite images."""

from images import ImageCollection
from tabs.actions import FavoriteActions
from tabs.gallery import ImageGallery
from tabs.shared import SearchFilter, VisiaTab


class FavoritesTab(VisiaTab):
    def render(self) -> None:
        actions = FavoriteActions(self.api)
        favorites = ImageCollection.visible(self.api, self.files).only(actions.favorite_names())
        collection = SearchFilter(
            self.layout,
            key="favorite_name_search",
            label="Search Favorites by image name",
            no_match_message="No favorite filenames or tags match your search.",
        ).apply(favorites)
        if collection is not None:
            ImageGallery(self.context, actions).render(collection)
