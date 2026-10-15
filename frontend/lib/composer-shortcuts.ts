"use client";
import {useRef,type KeyboardEvent} from 'react';

export const COMPOSER_KEY_HINT='Enter 提交；Alt+Enter / Ctrl+Enter 换行';

export function useComposerShortcuts(){
 const composing=useRef(false);
 return (change:(value:string)=>void,submit:()=>void,canSubmit:boolean)=>({
  onCompositionStart:()=>{composing.current=true;},
  onCompositionEnd:()=>{composing.current=false;},
  onKeyDown:(event:KeyboardEvent<HTMLTextAreaElement>)=>{
   const input=event.currentTarget;
   if(event.key!=='Enter'||event.shiftKey||event.metaKey||input.disabled||input.readOnly)return;
   if(composing.current||event.nativeEvent.isComposing||event.nativeEvent.keyCode===229)return;
   event.preventDefault();
   if(event.altKey||event.ctrlKey){
    const next=input.value.slice(0,input.selectionStart)+'\n'+input.value.slice(input.selectionEnd);
    if(input.maxLength>=0&&next.length>input.maxLength)return;
    input.setRangeText('\n',input.selectionStart,input.selectionEnd,'end');
    change(next);
   }else if(canSubmit&&!event.repeat)submit();
  },
 });
}
