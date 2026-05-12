import { useMemo } from 'react';
import type { CSSProperties } from 'react';
import './walking-person.css';

export type WalkingPersonProps = {
    /** Текущее время сцены (мс от общего старта) */
    sceneTimeMs: number;
    /** Когда должен оказаться на точке */
    arrivalTimeMs: number;
    /** Когда уходит с точки */
    departureTimeMs: number;
    /** Координаты точки (px), родитель с position: relative */
    targetX: number;
    targetY: number;
    /** Откуда выходит на подход (px). По умолчанию слева от цели */
    fromX?: number;
    fromY?: number;
    /** Куда уходит (px). По умолчанию как from */
    exitX?: number;
    exitY?: number;
    /** Длительность подхода и ухода, мс */
    walkDurationMs?: number;
    className?: string;
    /** Подпись над головой (id для экрана) */
    label?: string;
    /** Подсказка при подстановке id вместо «имени» из API */
    labelTitle?: string;
    /** Цвет «футболки» пастельный */
    shirtColor?: string;
};

function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
}

function clamp01(value: number): number {
    return Math.min(1, Math.max(0, value));
}

/** Лёгкая задержка «танца», чтобы сотрудники на смене не двигались синхронно. */
function danceDelayFromLabel(label: string | undefined): number {
    if (!label) {
        return 0;
    }
    let h = 0;
    for (let i = 0; i < label.length; i += 1) {
        h = (h + label.charCodeAt(i) * (i + 1)) % 997;
    }
    return (h % 20) * 0.035;
}

export function WalkingPerson({
    sceneTimeMs,
    arrivalTimeMs,
    departureTimeMs,
    targetX,
    targetY,
    fromX: fromXProp,
    fromY: fromYProp,
    exitX: exitXProp,
    exitY: exitYProp,
    walkDurationMs = 2000,
    className = '',
    label,
    labelTitle,
    shirtColor = '#8ec5f0',
}: WalkingPersonProps) {
    const fromX = fromXProp ?? targetX - 80;
    const fromY = fromYProp ?? targetY;
    const exitX = exitXProp ?? fromX;
    const exitY = exitYProp ?? fromY;

    const state = useMemo(() => {
        const walkInStart = arrivalTimeMs - walkDurationMs;
        const walkOutEnd = departureTimeMs + walkDurationMs;

        if (sceneTimeMs < walkInStart || sceneTimeMs >= walkOutEnd) {
            return { visible: false, x: fromX, y: fromY, walking: false };
        }

        if (sceneTimeMs < arrivalTimeMs) {
            const rawT = (sceneTimeMs - walkInStart) / walkDurationMs;
            const t = clamp01(rawT);
            return {
                visible: true,
                x: lerp(fromX, targetX, t),
                y: lerp(fromY, targetY, t),
                walking: true,
            };
        }

        if (sceneTimeMs < departureTimeMs) {
            return {
                visible: true,
                x: targetX,
                y: targetY,
                walking: false,
            };
        }

        const rawT = (sceneTimeMs - departureTimeMs) / walkDurationMs;
        const t = clamp01(rawT);
        return {
            visible: true,
            x: lerp(targetX, exitX, t),
            y: lerp(targetY, exitY, t),
            walking: true,
        };
    }, [
        sceneTimeMs,
        arrivalTimeMs,
        departureTimeMs,
        targetX,
        targetY,
        fromX,
        fromY,
        exitX,
        exitY,
        walkDurationMs,
    ]);

    if (!state.visible) {
        return null;
    }

    const rootClass = [
        'walking-person',
        state.walking ? 'walking-person--walking' : 'walking-person--idle',
        className,
    ]
        .filter(Boolean)
        .join(' ');

    const danceDelay = danceDelayFromLabel(label);

    const styleVars = {
        '--walk-shirt': shirtColor,
        '--dance-delay': `${danceDelay}s`,
    } as CSSProperties;

    return (
        <div
            className={rootClass}
            style={{
                left: state.x,
                top: state.y,
                ...styleVars,
            }}
        >
            <div className="walking-person__figure">
                {label ? (
                    <span className="walking-person__id" title={labelTitle ?? label}>
                        {label}
                    </span>
                ) : null}
                <div className="walking-person__head">
                    <span className="walking-person__hair" aria-hidden />
                    <span className="walking-person__blush walking-person__blush--l" aria-hidden />
                    <span className="walking-person__blush walking-person__blush--r" aria-hidden />
                    <span className="walking-person__eye walking-person__eye--l" aria-hidden>
                        <span className="walking-person__eye-shine" aria-hidden />
                    </span>
                    <span className="walking-person__eye walking-person__eye--r" aria-hidden>
                        <span className="walking-person__eye-shine" aria-hidden />
                    </span>
                    <span className="walking-person__smile" aria-hidden />
                </div>
                <div className="walking-person__torso">
                    <span className="walking-person__arm walking-person__arm--left" />
                    <div className="walking-person__body" />
                    <span className="walking-person__arm walking-person__arm--right" />
                </div>
                <div className="walking-person__legs">
                    <span className="walking-person__leg walking-person__leg--left" />
                    <span className="walking-person__leg walking-person__leg--right" />
                </div>
            </div>
        </div>
    );
}

export default WalkingPerson;
