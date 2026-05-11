import { useCallback, useEffect, useState } from 'react';
import './playback-bar.css';

const RAIL_WIDTH_PX = Math.round(1091 * 1.5);
const RAIL_HEIGHT_PX = 14;
/** Основной фон дорожки */
const TRACK_COLOR = '#FFC18A';
/** Пройденный участок */
const PROGRESS_COLOR = '#ff3b3b';

export type PlaybackBarProps = {
    currentIndex: number;
    slideCount: number;
    isPaused: boolean;
    onPauseToggle: () => void;
    onPrevHour: () => void;
    onNextHour: () => void;
    onSeek: (index: number) => void;
};

function PlaybackBar({
    currentIndex,
    slideCount,
    isPaused,
    onPauseToggle,
    onPrevHour,
    onNextHour,
    onSeek,
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

    return (
        <div className="playback-bar">
            <div
                className="playback-bar__rail"
                style={{
                    width: RAIL_WIDTH_PX,
                    maxWidth: '100%',
                    height: RAIL_HEIGHT_PX,
                }}
            >
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

            <div className="playback-bar__controls">
                <button
                    type="button"
                    className="playback-bar__btn"
                    onClick={onPrevHour}
                    disabled={sliderDisabled}
                    aria-label="Предыдущий час"
                >
                    <i className="bi bi-rewind-fill" />
                </button>
                <button
                    type="button"
                    className="playback-bar__btn"
                    onClick={onPauseToggle}
                    disabled={slideCount === 0}
                    aria-label={isPaused ? 'Продолжить' : 'Пауза'}
                >
                    <i className={isPaused ? 'bi bi-play-fill' : 'bi bi-pause-fill'} />
                </button>
                <button
                    type="button"
                    className="playback-bar__btn"
                    onClick={onNextHour}
                    disabled={sliderDisabled}
                    aria-label="Следующий час"
                >
                    <i className="bi bi-fast-forward-fill" />
                </button>
            </div>
        </div>
    );
}

export default PlaybackBar;
