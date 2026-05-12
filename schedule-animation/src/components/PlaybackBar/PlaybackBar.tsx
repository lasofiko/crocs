import { useCallback, useEffect, useState } from 'react';
import './playback-bar.css';

const RAIL_HEIGHT_PX = 13;
const TRACK_COLOR = 'rgb(255 210 175 / 72%)';
const PROGRESS_COLOR = '#d9732b';

export type PlaybackSpeed = 1 | 2 | 3;

export type PlaybackBarProps = {
    currentIndex: number;
    slideCount: number;
    isPaused: boolean;
    playbackSpeed: PlaybackSpeed;
    onPlaybackSpeedChange: (speed: PlaybackSpeed) => void;
    onPauseToggle: () => void;
    onPrevHour: () => void;
    onNextHour: () => void;
    onSeek: (index: number) => void;
    /** Экспорт Excel — кнопка справа в нижней панели рядом с таймлайном */
    onExportSchedule?: () => void;
};

function PlaybackBar({
    currentIndex,
    slideCount,
    isPaused,
    playbackSpeed,
    onPlaybackSpeedChange,
    onPauseToggle,
    onPrevHour,
    onNextHour,
    onSeek,
    onExportSchedule,
}: PlaybackBarProps) {
    const max = Math.max(0, slideCount - 1);
    const sliderDisabled = slideCount <= 1;
    const fillPercent = max === 0 ? 0 : (currentIndex / max) * 100;

    const [isDragging, setIsDragging] = useState(false);

    const endDrag = useCallback(() => {
        setIsDragging(false);
    }, []);

    useEffect(() => {
        if (!isDragging) {
            return undefined;
        }

        window.addEventListener('pointerup', endDrag);
        window.addEventListener('pointercancel', endDrag);

        return () => {
            window.removeEventListener('pointerup', endDrag);
            window.removeEventListener('pointercancel', endDrag);
        };
    }, [isDragging, endDrag]);

    const transitionEase = '0.48s cubic-bezier(0.22, 1, 0.36, 1)';
    const fillTransition = isDragging ? 'none' : `width ${transitionEase}`;
    const thumbTransition = isDragging ? 'none' : `left ${transitionEase}`;

    const speeds: PlaybackSpeed[] = [1, 2, 3];

    return (
        <div className="playback-bar">
            <div className="playback-bar__inner">
                <div className="playback-bar__rail" style={{ height: RAIL_HEIGHT_PX }}>
                    <div className="playback-bar__track-bg" style={{ backgroundColor: TRACK_COLOR }} />

                    <div
                        className="playback-bar__track-fill"
                        style={{
                            width: `${fillPercent}%`,
                            backgroundColor: PROGRESS_COLOR,
                            transition: fillTransition,
                        }}
                    />

                    <div
                        className="playback-bar__thumb"
                        style={{
                            left: `${fillPercent}%`,
                            transform: 'translate(-50%, -50%)',
                            transition: thumbTransition,
                        }}
                    />

                    <input
                        type="range"
                        className="playback-bar__range"
                        min={0}
                        max={max}
                        step={1}
                        value={Math.min(currentIndex, max)}
                        disabled={sliderDisabled}
                        onPointerDown={() => setIsDragging(true)}
                        onPointerUp={endDrag}
                        onChange={(event) => onSeek(Number(event.target.value))}
                        aria-label="Позиция по расписанию"
                    />
                </div>

                <div className="playback-bar__row">
                    <div className="playback-bar__speed" role="group" aria-label="Скорость">
                        <span className="playback-bar__speed-label">скорость</span>
                        <span className="playback-bar__speed-btns">
                            {speeds.map((s) => (
                                <button
                                    key={s}
                                    type="button"
                                    className={`playback-bar__speed-btn${playbackSpeed === s ? ' playback-bar__speed-btn--active' : ''}`}
                                    onClick={() => onPlaybackSpeedChange(s)}
                                    aria-pressed={playbackSpeed === s}
                                >
                                    {s}x
                                </button>
                            ))}
                        </span>
                    </div>

                    <div className="playback-bar__controls">
                        <button
                            type="button"
                            className="playback-bar__btn playback-bar__btn--side"
                            onClick={onPrevHour}
                            disabled={sliderDisabled}
                            aria-label="Предыдущий час"
                        >
                            <i className="bi bi-rewind-fill" />
                        </button>
                        <button
                            type="button"
                            className="playback-bar__btn playback-bar__btn--play"
                            onClick={onPauseToggle}
                            disabled={slideCount === 0}
                            aria-label={isPaused ? 'Продолжить' : 'Пауза'}
                        >
                            <i className={isPaused ? 'bi bi-play-fill' : 'bi bi-pause-fill'} />
                        </button>
                        <button
                            type="button"
                            className="playback-bar__btn playback-bar__btn--side"
                            onClick={onNextHour}
                            disabled={sliderDisabled}
                            aria-label="Следующий час"
                        >
                            <i className="bi bi-fast-forward-fill" />
                        </button>
                    </div>

                    {onExportSchedule ? (
                        <div className="playback-bar__export-wrap">
                            <button
                                type="button"
                                className="playback-bar__export"
                                onClick={onExportSchedule}
                                aria-label="Экспорт расписания в Excel"
                            >
                                <i className="bi bi-download playback-bar__export-icon" aria-hidden />
                                <span className="playback-bar__export-text">
                                    <span className="playback-bar__export-line">Экспорт</span>
                                    <span className="playback-bar__export-sub">расписания</span>
                                </span>
                            </button>
                        </div>
                    ) : (
                        <div className="playback-bar__row-spacer" aria-hidden />
                    )}
                </div>
            </div>
        </div>
    );
}

export default PlaybackBar;
