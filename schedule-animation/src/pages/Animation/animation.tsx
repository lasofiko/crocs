import { useEffect, useState } from 'react';
import './animation.css';
import { fetchAnimationSchedule, fetchScheduleExcel } from '../../api/scheduleApi';
import Header from '../../components/Header/header';
import type { AnimationScheduleItem } from '../../types/schedule';
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

    const headerData = scheduleData[currentIndex] ?? DEFAULT_HEADER_DATA;
    const isWorkingTime = headerData.hour >= WORK_START_HOUR && headerData.hour <= WORK_END_HOUR;

    useEffect(() => {
        fetchAnimationSchedule()
            .then((schedule) => {
                if (schedule.length > 0) {
                    setScheduleData(schedule);
                    setCurrentIndex(getStartIndex(schedule));
                }
            })
            .catch(() => {
                setScheduleData([DEFAULT_HEADER_DATA]);
                setCurrentIndex(0);
            });
    }, []);

    useEffect(() => {
        const intervalId = window.setInterval(() => {
            setCurrentIndex((index) => (index + 1) % scheduleData.length);
        }, SLIDE_DURATION);

        return () => window.clearInterval(intervalId);
    }, [scheduleData.length]);

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

    return(
        <main className={`animation${isWorkingTime ? '' : ' animation--dimmed'}`}>
            <Header
                day={isWorkingTime ? formatDay(headerData.day) : ''}
                time={formatHour(headerData.hour)}
                guestsCount={isWorkingTime ? headerData.expectedPeopleCount : null}
                onSaveSchedule={handleSaveSchedule}
            />
        </main>
    )
}

export default Animation;