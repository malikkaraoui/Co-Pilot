"""Tests du systeme de scoring et filtrage de videos YouTube."""

from app.services.youtube_service import (
    _score_video_relevance,
    filter_and_rank_videos,
)


class TestScoreVideoRelevance:
    """Tests du scoring de pertinence."""

    def test_perfect_video_trusted_channel(self):
        """Video parfaite d'une chaine de confiance."""
        video = {
            "title": "Essai Peugeot 308 2024",
            "channel": "L'argus",
            "duration": 600,  # 10 min
            "view_count": 150000,
            "like_count": 5000,  # 3.3% ratio
            "channel_follower_count": 500000,
            "channel_is_verified": True,
            "upload_date": "20240315",
        }
        score = _score_video_relevance(video, vehicle_year=2024)
        # Score attendu: 30 (duree) + 20 (vues) + 15 (like ratio) + 25 (trusted channel) + 20 (fraicheur) + 10 (keywords) = 100+
        assert score >= 95

    def test_short_video_excluded(self):
        """Short (<60s) doit etre exclu (score 0)."""
        video = {"title": "Peugeot 308 #short", "duration": 45, "channel": "TestChannel"}
        score = _score_video_relevance(video)
        assert score == 0.0

    def test_long_video_excluded(self):
        """Video trop longue (>45min) doit etre exclue."""
        video = {"title": "Peugeot 308 livestream", "duration": 3000, "channel": "TestChannel"}
        score = _score_video_relevance(video)
        assert score == 0.0

    def test_pre_launch_presentation_excluded(self):
        """Presentation avant sortie doit etre exclue."""
        video = {
            "title": "Présentation mondiale de la Peugeot 308",
            "duration": 600,
            "channel": "Auto Moto",
            "view_count": 100000,
        }
        score = _score_video_relevance(video)
        assert score == 0.0

    def test_optimal_duration_bonus(self):
        """Duree optimale (6-25 min) doit donner le meilleur score."""
        video_optimal = {"title": "Test", "duration": 900, "channel": "Ch"}  # 15 min
        video_short = {"title": "Test", "duration": 200, "channel": "Ch"}  # 3 min
        video_long = {"title": "Test", "duration": 2000, "channel": "Ch"}  # 33 min

        score_optimal = _score_video_relevance(video_optimal)
        score_short = _score_video_relevance(video_short)
        score_long = _score_video_relevance(video_long)

        assert score_optimal > score_short
        assert score_optimal > score_long

    def test_trusted_channel_bonus(self):
        """Chaine de confiance doit donner un gros bonus."""
        video_trusted = {
            "title": "Essai",
            "duration": 600,
            "channel": "Fiches auto",
            "view_count": 10000,
        }
        video_random = {
            "title": "Essai",
            "duration": 600,
            "channel": "Random Guy",
            "view_count": 10000,
        }

        score_trusted = _score_video_relevance(video_trusted)
        score_random = _score_video_relevance(video_random)

        assert score_trusted > score_random + 20  # Au moins 25 points de diff

    def test_freshness_bonus_with_vehicle_year(self):
        """Video recente apres sortie du modele doit avoir un bonus."""
        video_fresh = {
            "title": "Test",
            "duration": 600,
            "channel": "Ch",
            "upload_date": "20240601",
        }
        video_old = {
            "title": "Test",
            "duration": 600,
            "channel": "Ch",
            "upload_date": "20200101",
        }

        score_fresh = _score_video_relevance(video_fresh, vehicle_year=2024)
        score_old = _score_video_relevance(video_old, vehicle_year=2024)

        assert score_fresh > score_old

    def test_keywords_in_title_bonus(self):
        """Mots-cles pertinents dans le titre donnent un bonus."""
        video_with_keywords = {
            "title": "Essai complet Peugeot 308",
            "duration": 600,
            "channel": "Ch",
        }
        video_without_keywords = {"title": "Peugeot 308", "duration": 600, "channel": "Ch"}

        score_with = _score_video_relevance(video_with_keywords)
        score_without = _score_video_relevance(video_without_keywords)

        assert score_with > score_without

    def test_focus_channel_massive_bonus(self):
        """Chaine focus doit recevoir un bonus massif (+50 pts)."""
        video_focus = {
            "title": "Test",
            "duration": 600,
            "channel": "Ma Chaine Preferee",
            "view_count": 1000,
        }
        video_random = {
            "title": "Test",
            "duration": 600,
            "channel": "Random Channel",
            "view_count": 1000,
        }

        score_focus = _score_video_relevance(video_focus, focus_channels=["Ma Chaine Preferee"])
        score_random = _score_video_relevance(video_random, focus_channels=["Ma Chaine Preferee"])

        assert score_focus > score_random + 45  # Au moins 50 pts de difference

    def test_focus_channel_partial_match(self):
        """Chaine focus doit matcher partiellement (case insensitive)."""
        video = {
            "title": "Test",
            "duration": 600,
            "channel": "L'argus",
            "view_count": 1000,
        }

        score_exact = _score_video_relevance(video, focus_channels=["L'argus"])
        score_partial = _score_video_relevance(video, focus_channels=["argus"])
        score_case = _score_video_relevance(video, focus_channels=["L'ARGUS"])

        # Tous doivent matcher
        assert score_exact > 50
        assert score_partial > 50
        assert score_case > 50


class TestFilterAndRankVideos:
    """Tests du filtrage et classement de videos."""

    def test_filters_shorts(self):
        """Les shorts doivent etre filtres."""
        videos = [
            {"id": "1", "title": "Short", "duration": 45, "channel": "Ch"},
            {"id": "2", "title": "Normal", "duration": 600, "channel": "Ch"},
        ]
        result = filter_and_rank_videos(videos)
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_filters_pre_launch_videos(self):
        """Les presentations pre-sortie doivent etre filtrees."""
        videos = [
            {"id": "1", "title": "Salon de l'auto - Peugeot 308", "duration": 600, "channel": "Ch"},
            {"id": "2", "title": "Essai Peugeot 308", "duration": 600, "channel": "Ch"},
        ]
        result = filter_and_rank_videos(videos)
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_ranks_by_score(self):
        """Les videos doivent etre classees par score decroissant."""
        videos = [
            {
                "id": "low",
                "title": "Test",
                "duration": 600,
                "channel": "Random",
                "view_count": 1000,
            },
            {
                "id": "high",
                "title": "Essai",
                "duration": 600,
                "channel": "L'argus",
                "view_count": 100000,
                "like_count": 3000,
                "channel_follower_count": 500000,
            },
        ]
        result = filter_and_rank_videos(videos, max_results=2)
        assert result[0]["id"] == "high"
        assert result[1]["id"] == "low"
        assert result[0]["relevance_score"] > result[1]["relevance_score"]

    def test_respects_max_results(self):
        """Ne doit retourner que max_results videos."""
        videos = [
            {"id": f"v{i}", "title": "Test", "duration": 600, "channel": "Ch"} for i in range(10)
        ]
        result = filter_and_rank_videos(videos, max_results=3)
        assert len(result) == 3

    def test_adds_relevance_score_field(self):
        """Doit ajouter le champ relevance_score a chaque video."""
        videos = [{"id": "1", "title": "Essai", "duration": 600, "channel": "Ch"}]
        result = filter_and_rank_videos(videos)
        assert "relevance_score" in result[0]
        assert isinstance(result[0]["relevance_score"], float)

    def test_focus_channels_priority(self):
        """Videos des chaines focus doivent etre en tete du classement."""
        videos = [
            {
                "id": "random",
                "title": "Essai",
                "duration": 600,
                "channel": "Random",
                "view_count": 500000,  # Beaucoup de vues mais pas focus
                "like_count": 20000,
            },
            {
                "id": "focus",
                "title": "Test",
                "duration": 600,
                "channel": "Fiches auto",
                "view_count": 10000,  # Moins de vues mais focus
            },
        ]
        result = filter_and_rank_videos(videos, focus_channels=["Fiches auto"], max_results=2)
        # La video focus doit etre en premiere position malgre moins de vues
        assert result[0]["id"] == "focus"
        assert result[1]["id"] == "random"
