import { useMemo } from 'react';
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
};

function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
}

function clamp01(value: number): number {
    return Math.min(1, Math.max(0, value));
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

    const rootClass = ['walking-person', state.walking ? 'walking-person--walking' : '', className]
        .filter(Boolean)
        .join(' ');

    return (
        <div
            className={rootClass}
            style={{
                left: state.x,
                top: state.y,
            }}
        >
            <div className="walking-person__figure">
                <div className="walking-person__head" />
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
