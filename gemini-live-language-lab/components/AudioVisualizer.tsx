import React, { useEffect, useRef } from 'react';

interface AudioVisualizerProps {
  analyzer: AnalyserNode | null;
  color?: string;
}

export const AudioVisualizer: React.FC<AudioVisualizerProps> = ({ analyzer, color = '#06b6d4' }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!analyzer || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
    };
    resizeCanvas();
    
    const resizeObserver = new ResizeObserver(resizeCanvas);
    resizeObserver.observe(canvas);

    const bufferLength = analyzer.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    let animationId: number;

    const draw = () => {
      animationId = requestAnimationFrame(draw);
      analyzer.getByteFrequencyData(dataArray);

      // Clear canvas with transparency
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Draw waveform bars in the center
      const barWidth = (canvas.width / bufferLength) * 2.5;
      const centerY = canvas.height / 2;
      const maxBarHeight = canvas.height * 0.3;
      
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * maxBarHeight;
        
        // Create gradient for bars
        const gradient = ctx.createLinearGradient(0, centerY - barHeight/2, 0, centerY + barHeight/2);
        gradient.addColorStop(0, color + '40');
        gradient.addColorStop(0.5, color + '80');
        gradient.addColorStop(1, color + '40');
        
        ctx.fillStyle = gradient;
        
        // Draw centered bars
        ctx.fillRect(x, centerY - barHeight/2, barWidth - 1, barHeight);
        
        // Add glow effect for louder frequencies
        if (dataArray[i] > 200) {
          ctx.shadowBlur = 15;
          ctx.shadowColor = color;
          ctx.fillRect(x, centerY - barHeight/2, barWidth - 1, 2);
          ctx.shadowBlur = 0;
        }

        x += barWidth;
      }
    };

    draw();
    
    return () => {
      cancelAnimationFrame(animationId);
      resizeObserver.disconnect();
    };
  }, [analyzer, color]);

  return (
    <canvas 
      ref={canvasRef} 
      className="absolute inset-0 w-full h-full opacity-80"
    />
  );
};
