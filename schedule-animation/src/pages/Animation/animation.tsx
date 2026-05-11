import { useEffect, useMemo, useState } from 'react';
import './animation.css';
import { fetchAnimationSchedule, fetchScheduleExcel } from '../../api/scheduleApi';
import Header from '../../components/Header/header';
import PlaybackBar from '../../components/PlaybackBar/PlaybackBar';
import type { AnimationScheduleItem } from '../../types/schedule';
import {
    buildHourBoundaryIndices,
    nextHourStartIndex,
    prevHourStartIndex,
} from '../../utils/hourBoundaries';
import { filterValidScheduleRows } from '../../utils/filterValidScheduleRows';
import { formatDay, formatHour } from '../../utils/scheduleFormat';

const DEFAULT_HEADER_DATA: AnimationScheduleItem = {
    date: '',
    hour: 7,
    station: '',
    employeeIds: [],
    expectedPeopleCount: 0,
    expectationIndicator: '',
    day: 1,
};

const SLIDE_DURATION = 3000;
const WORK_START_HOUR = 7;
const WORK_END_HOUR = 23;

function getStartIndex(schedule: AnimationScheduleItem[]): number {
    const mondayStartIndex = schedule.findIndex((item) => item.day === 1 && item.hour === WORK_START_HOUR);

    return mondayStartIndex === -1 ? 0 : mondayStartIndex;
}

function Animation() {
    const [scheduleData, setScheduleData] = useState<AnimationScheduleItem[]>([DEFAULT_HEADER_DATA]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isPaused, setIsPaused] = useState(false);

    const hourBoundaries = useMemo(() => buildHourBoundaryIndices(scheduleData), [scheduleData]);

    const headerData = scheduleData[currentIndex] ?? DEFAULT_HEADER_DATA;
    const isWorkingTime = headerData.hour >= WORK_START_HOUR && headerData.hour <= WORK_END_HOUR;

    useEffect(() => {
        const apiBase = import.meta.env.VITE_API_URL?.trim() ?? '';

        if (!apiBase) {
            setScheduleData([DEFAULT_HEADER_DATA]);
            setCurrentIndex(0);
            return;
        }

        fetchAnimationSchedule()
            .then((schedule) => {
                const valid = filterValidScheduleRows(schedule);

                if (valid.length > 0) {
                    setScheduleData(valid);
                    setCurrentIndex(getStartIndex(valid));
                } else {
                    setScheduleData([DEFAULT_HEADER_DATA]);
                    setCurrentIndex(0);
                }
            })
            .catch(() => {
                setScheduleData([DEFAULT_HEADER_DATA]);
                setCurrentIndex(0);
            });
    }, []);

    useEffect(() => {
        if (isPaused || scheduleData.length <= 1) {
            return undefined;
        }

        const intervalId = window.setInterval(() => {
            setCurrentIndex((index) => (index + 1) % scheduleData.length);
        }, SLIDE_DURATION);

        return () => window.clearInterval(intervalId);
    }, [isPaused, scheduleData.length]);

    const handleSaveSchedule = () => {
        fetchScheduleExcel()
            .then((file) => {
                const fileUrl = URL.createObjectURL(file);
                const link = document.createElement('a');

                link.href = fileUrl;
                link.download = 'schedule.xlsx';
                link.click();
                URL.revokeObjectURL(fileUrl);
            })
            .catch(() => {});
    };

    const handleSeek = (index: number) => {
        setCurrentIndex(Math.max(0, Math.min(index, scheduleData.length - 1)));
    };

    const handlePrevHour = () => {
        setCurrentIndex((index) => prevHourStartIndex(hourBoundaries, index));
    };

    const handleNextHour = () => {
        setCurrentIndex((index) => nextHourStartIndex(hourBoundaries, index));
    };

    return (
        <main className="animation">
            <Header
                day={isWorkingTime ? formatDay(headerData.day) : ''}
                time={formatHour(headerData.hour)}
                guestsCount={isWorkingTime ? headerData.expectedPeopleCount : null}
                onSaveSchedule={handleSaveSchedule}
                screenDimmed={!isWorkingTime}
            />

            <section className="animation__stations" aria-label="Станции">
                {/* Карточки станций и WalkingPerson — по данным с бэка */}
            </section>

            <PlaybackBar
                currentIndex={currentIndex}
                slideCount={scheduleData.length}
                isPaused={isPaused}
                onPauseToggle={() => setIsPaused((value) => !value)}
                onPrevHour={handlePrevHour}
                onNextHour={handleNextHour}
                onSeek={handleSeek}
            />
        </main>
    );
}

export default Animation;
