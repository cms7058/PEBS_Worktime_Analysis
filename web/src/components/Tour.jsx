import { useEffect, useLayoutEffect, useState } from 'react'
import { useI18n } from '../i18n.jsx'

// 交互式引导：按教程步骤切换页签、高亮目标元素、显示说明气泡。
// tutorial: { title, steps: [{tab, selector, title, body}] }
export default function Tour({ tutorial, onTabChange, onClose }) {
  const { t } = useI18n()
  const [idx, setIdx] = useState(0)
  const [rect, setRect] = useState(null)
  const step = tutorial.steps[idx]

  // 进入步骤：先切页签，再定位目标元素（重试等待渲染）
  useLayoutEffect(() => {
    let cancelled = false
    if (step.tab) onTabChange(step.tab)
    const locate = (tries) => {
      if (cancelled) return
      const el = document.querySelector(step.selector)
      if (el) {
        el.scrollIntoView({ block: 'center', behavior: 'smooth' })
        setTimeout(() => {
          if (!cancelled) setRect(el.getBoundingClientRect())
        }, 350)
      } else if (tries > 0) {
        setTimeout(() => locate(tries - 1), 250)
      } else {
        setRect(null)   // 找不到元素时降级为居中气泡
      }
    }
    setRect(undefined)   // undefined = 定位中
    locate(12)
    return () => { cancelled = true }
  }, [idx, step, onTabChange])

  // 窗口变化时重新定位
  useEffect(() => {
    const onResize = () => {
      const el = document.querySelector(step.selector)
      if (el) setRect(el.getBoundingClientRect())
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [step])

  if (rect === undefined) return null   // 定位中不渲染，避免闪烁

  const pad = 6
  const hl = rect && {
    left: rect.left - pad, top: rect.top - pad,
    width: rect.width + pad * 2, height: rect.height + pad * 2,
  }
  // 气泡位置：目标下方放不下就放上方；无目标时居中
  const bubbleStyle = hl
    ? (hl.top + hl.height + 180 < window.innerHeight
        ? { left: Math.min(hl.left, window.innerWidth - 360), top: hl.top + hl.height + 12 }
        : { left: Math.min(hl.left, window.innerWidth - 360), top: Math.max(12, hl.top - 190) })
    : { left: '50%', top: '40%', transform: 'translate(-50%, -50%)' }

  return (
    <div className="tour-layer">
      {hl && <div className="tour-highlight" style={hl} />}
      <div className="tour-bubble" style={bubbleStyle}>
        <div className="tour-bubble-head">
          <b>{step.title}</b>
          <span className="hint">{idx + 1} / {tutorial.steps.length}</span>
        </div>
        <p>{step.body}</p>
        <div className="tour-bubble-actions">
          <button className="ghost" onClick={onClose}>{t('结束教程')}</button>
          <span style={{ flex: 1 }} />
          {idx > 0 && (
            <button className="ghost" onClick={() => setIdx(idx - 1)}>{t('上一步')}</button>
          )}
          {idx < tutorial.steps.length - 1 ? (
            <button className="primary" onClick={() => setIdx(idx + 1)}>{t('下一步')}</button>
          ) : (
            <button className="primary" onClick={onClose}>{t('完成')}</button>
          )}
        </div>
      </div>
    </div>
  )
}
