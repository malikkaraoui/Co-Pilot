"""Modeles YouTubeVideo et YouTubeTranscript.

On indexe des videos YouTube pertinentes pour chaque vehicule (essais,
retours proprietaires, comparatifs) et on extrait leurs sous-titres.
Les transcripts sont ensuite envoyes a Gemini pour generer les syntheses
(voir VehicleSynthesis). Les videos archivees (is_archived) sont exclues
du pipeline de synthese, les featured sont mises en avant dans le rapport.
"""

from datetime import datetime, timezone

from app.extensions import db


class YouTubeVideo(db.Model):
    """Video YouTube indexee pour un vehicule.

    Le video_id est l'identifiant YouTube (11 caracteres). La relation 1:1
    avec YouTubeTranscript est geree via uselist=False + cascade delete.
    Le vehicle_id est nullable car on peut indexer une video avant de
    l'avoir rattachee a un vehicule en base.
    """

    __tablename__ = "youtube_videos"
    __table_args__ = (db.UniqueConstraint("video_id", name="uq_yt_video_id"),)

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(20), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    channel_name = db.Column(db.String(200))
    duration_seconds = db.Column(db.Integer)
    published_at = db.Column(db.DateTime)
    search_query = db.Column(db.String(300))
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    transcript = db.relationship(
        "YouTubeTranscript", backref="video", uselist=False, cascade="all, delete-orphan"
    )
    vehicle = db.relationship("Vehicle", backref="youtube_videos")

    def __repr__(self):
        return f"<YouTubeVideo {self.video_id} {self.title[:40]}>"


class YouTubeTranscript(db.Model):
    """Sous-titres extraits d'une video YouTube.

    Le full_text contient le transcript complet concatene.
    Les snippets_json contiennent les segments avec timestamps
    pour pouvoir citer des passages precis dans la synthese.
    Le status suit le cycle : pending -> done | error.
    is_generated indique si les sous-titres sont auto-generes par YouTube
    (moins fiables) ou fournis manuellement par le createur.
    """

    __tablename__ = "youtube_transcripts"

    id = db.Column(db.Integer, primary_key=True)
    video_db_id = db.Column(
        db.Integer, db.ForeignKey("youtube_videos.id"), nullable=False, unique=True
    )
    language = db.Column(db.String(20), nullable=False)
    is_generated = db.Column(db.Boolean, default=True)
    full_text = db.Column(db.Text, nullable=False)
    snippets_json = db.Column(db.JSON)
    snippet_count = db.Column(db.Integer, default=0)
    char_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), nullable=False, default="pending")
    error_message = db.Column(db.Text)
    extracted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<YouTubeTranscript video={self.video_db_id} status={self.status}>"
