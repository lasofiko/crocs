import { useEffect, useState, type CSSProperties } from 'react';
import type { AnimationScheduleItem } from '../../types/schedule';
import WalkingPerson from '../WalkingPerson/WalkingPerson';
import { staffingTone, type StaffingTone } from '../../utils/staffingTone';
import './week-stations-board.css';

type WeekStationsBoardProps = {
    items: AnimationScheduleItem[];
};

type StationSpot = {
    leftPct: number;
    topPct: number;
    badgeDx?: number;
    badgeDy?: number;
    /** С какой стороны подходят к прилавку (по горизонтали в локальных px узла) */
    walkFromSide?: 'left' | 'right';
};

const STATION_LAYOUT: Record<string, StationSpot> = {
    // Привязка к розовым прилавкам на фоне (проценты от сцены).
    // K — сверху по центру; FF — правый верхний; BVR — верхний левый;
    // C — нижний левый; TS — нижний правый.
    K: { leftPct: 50, topPct: 30, badgeDx: 0, badgeDy: -26, walkFromSide: 'left' },
    FF: { leftPct: 96, topPct: 30, badgeDx: -54, badgeDy: -20, walkFromSide: 'left' },
    BVR: { leftPct: 5, topPct: 30, badgeDx: 2, badgeDy: -24, walkFromSide: 'left' },
    C: { leftPct: 15, topPct: 93, badgeDx: 4, badgeDy: 6, walkFromSide: 'left' },
    TS: { leftPct: 88, topPct: 95, badgeDx: -56, badgeDy: 6, walkFromSide: 'right' },
};

function actualCount(item: AnimationScheduleItem): number {
    if (item.atStationCount !== undefined && Number.isFinite(item.atStationCount)) {
        return item.atStationCount;
    }

    return item.employeeIds.length;
}

function toneLabel(tone: StaffingTone): string {
    if (tone === 'ok') return 'Норма';
    if (tone === 'warn') return 'Ниже нормы';
    return 'Критично';
}

function stationSpot(station: string, index: number): StationSpot {
    const fixed = STATION_LAYOUT[station.trim().toUpperCase()];
    if (fixed) {
        return fixed;
    }

    // fallback for unknown station names
    return {
        leftPct: 14 + (index % 5) * 18,
        topPct: 24 + Math.floor(index / 5) * 16,
    };
}

function WeekStationsBoard({ items }: WeekStationsBoardProps) {
    const [sceneTimeMs, setSceneTimeMs] = useState(0);

    useEffect(() => {
        const startedAt = Date.now();
        const timer = window.setInterval(() => {
            setSceneTimeMs(Date.now() - startedAt);
        }, 120);
        return () => window.clearInterval(timer);
    }, []);

    if (items.length === 0) {
        return (
            <div className="week-stations-board week-stations-board--empty">
                <p className="week-stations-board__empty">Нет данных по станциям за этот час.</p>
            </div>
        );
    }

    return (
        <div className="week-stations-board">
            <div className="week-stations-board__scene">
                {items.map((item, stationIdx) => {
                    const actual = actualCount(item);
                    const expected = Math.max(0, item.expectedPeopleCount);
                    const tone = staffingTone(expected, actual, item.expectationIndicator);
                    const peopleCount = item.employeeIds.length > 0 ? item.employeeIds.length : actual;
                    const spot = stationSpot(item.station, stationIdx);

                    return (
                        <article
                            key={`${item.day}-${item.hour}-${item.station}`}
                            className={`station-node station-node--${tone}`}
                            style={
                                {
                                    left: `${spot.leftPct}%`,
                                    top: `${spot.topPct}%`,
                                    '--badge-dx': `${spot.badgeDx ?? -6}px`,
                                    '--badge-dy': `${spot.badgeDy ?? -16}px`,
                                } as CSSProperties
                            }
                        >
                            <div className="station-node__counter" />
                            <div className="station-node__title">{item.station}</div>

                            <div className={`station-node__badge station-node__badge--${tone}`}>
                                <span className="station-node__actual">{actual}</span>
                                <span className="station-node__sep">/</span>
                                <span className="station-node__expected">{expected}</span>
                                <span className="station-node__unit"> чел</span>
                                <span className="station-node__status">{toneLabel(tone)}</span>
                            </div>

                            {item.employeeIds.length > 0 ? (
                                <div className="station-node__ids" title={item.employeeIds.join(', ')}>
                                    {item.employeeIds.slice(0, 7).join(', ')}
                                    {item.employeeIds.length > 7 ? '…' : ''}
                                </div>
                            ) : null}

                            {peopleCount > 0 ? (
                                <div
                                    className={`station-node__walkers station-node__walkers--from-${spot.walkFromSide ?? 'left'}`}
                                    aria-hidden="true"
                                >
                                    {Array.from({ length: Math.min(peopleCount, 24) }).map((_, idx) => {
                                        const lane = idx % 2;
                                        const col = Math.floor(idx / 2);
                                        const targetX = 4 + col * 14;
                                        const targetY = lane === 0 ? 20 : 38;
                                        const offset = (idx * 240) % 1800;
                                        const cycle = 5000;
                                        const phase = sceneTimeMs % cycle;
                                        const fromRight = spot.walkFromSide === 'right';
                                        const base = 80 + col * 9;
                                        const fromX = fromRight ? base : -base;
                                        const exitX = fromRight ? base + 6 : -base - 6;
                                        return (
                                            <WalkingPerson
                                                key={`${item.day}-${item.hour}-${item.station}-p${idx}`}
                                                sceneTimeMs={phase}
                                                arrivalTimeMs={900 + offset}
                                                departureTimeMs={3600 + offset}
                                                walkDurationMs={800}
                                                targetX={targetX}
                                                targetY={targetY}
                                                fromX={fromX}
                                                fromY={44 + lane * 6}
                                                exitX={exitX}
                                                exitY={46 + lane * 6}
                                            />
                                        );
                                    })}
                                </div>
                            ) : null}
                        </article>
                    );
                })}
            </div>
        </div>
    );
}

export default WeekStationsBoard;
