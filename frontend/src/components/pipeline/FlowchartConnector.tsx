interface FlowchartConnectorProps {
  completed: boolean;
  isPhase?: boolean;
}

export function FlowchartConnector({ completed, isPhase = false }: FlowchartConnectorProps) {
  const height = isPhase ? 32 : 20;
  const color = completed ? '#22c55e' : '#475569';

  return (
    <div className={`flex justify-center ${isPhase ? 'py-1' : 'py-0'}`}>
      <svg width="20" height={height} viewBox={`0 0 20 ${height}`} className="flex-shrink-0">
        <line
          x1="10" y1="0" x2="10" y2={height - 6}
          stroke={color}
          strokeWidth={isPhase ? 2.5 : 1.5}
          strokeDasharray={completed ? 'none' : '3 3'}
          strokeOpacity={completed ? 1 : 0.5}
        />
        <polygon
          points={`5,${height - 6} 10,${height} 15,${height - 6}`}
          fill={color}
          fillOpacity={completed ? 1 : 0.5}
        />
      </svg>
    </div>
  );
}
