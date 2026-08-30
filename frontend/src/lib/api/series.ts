import { client, BASE_URL } from './client';

/** A single episode within a series. */
export interface Episode {
  id: number;
  title: string;
  file_name: string;
  season_number: number | null;
  episode_number: number | null;
  duration: number | null;
  thumbnail_path: string | null;
  poster_path: string | null;
  rating: number | null;
  is_favorite: boolean;
  is_watched: boolean;
  playback_position: number;
  file_size: number | null;
  year: number | null;
  updated_at?: string;
}

/** A group of episodes belonging to the same season. */
export interface SeasonGroup {
  season_number: number;
  episode_count: number;
  episodes: Episode[];
}

/** Series list item (lightweight). */
export interface Series {
  id: number;
  library_id: number;
  title: string;
  tmdb_id: number | null;
  year: number | null;
  overview: string | null;
  poster_path: string | null;
  scrape_data: Record<string, unknown> | null;
  total_seasons: number | null;
  total_episodes: number | null;
  episode_count: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

/** Series detail with episodes grouped by season. */
export interface SeriesDetail extends Series {
  seasons: SeasonGroup[];
  unseasoned_episodes: Episode[];
}

/** Series list response (paginated). */
export interface SeriesListResponse {
  items: Series[];
  total: number;
  page: number;
  page_size: number;
}

/** Previous/next episode navigation result. */
export interface EpisodeNavigation {
  has_previous: boolean;
  has_next: boolean;
  previous_id: number | null;
  next_id: number | null;
  previous_title: string | null;
  next_title: string | null;
}

export const seriesApi = {
  /** List all series, optionally filtered by library. Paginated. */
  list: async (libraryId?: string, page: number = 1, pageSize: number = 60): Promise<SeriesListResponse> => {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (libraryId) params.library_id = libraryId;
    return client.get<SeriesListResponse>('/series', params);
  },

  /** Get series detail with episodes grouped by season. */
  get: async (id: string): Promise<SeriesDetail> =>
    client.get<SeriesDetail>(`/series/${id}`),

  /** Get previous/next episode navigation for a media within its series. */
  getEpisodeNav: async (mediaId: string): Promise<EpisodeNavigation> =>
    client.get<EpisodeNavigation>(`/series/episodes/${mediaId}/nav`),

  /** Build the poster URL for a series. */
  posterUrl: (id: string | number): string =>
    `${BASE_URL}/series/${id}/poster`,
};
