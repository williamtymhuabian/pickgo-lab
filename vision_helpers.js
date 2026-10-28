/* Shared image-coordinate and mask helpers; no dependencies or camera access. */
(function(root){
'use strict';
function apply_mask_rgba(source,mask){
  if(source.length!==mask.length||source.length%4)throw Error('Image and mask dimensions differ');
  const output=new Uint8ClampedArray(source);
  for(let i=0;i<output.length;i+=4)output[i+3]=mask[i]>0?source[i+3]:0;
  return output;
}
function image_point(clientX,clientY,rect,width,height){
  if(rect.width<=0||rect.height<=0)throw Error('Image is not visible');
  return [Math.max(0,Math.min(width,Math.round((clientX-rect.left)*width/rect.width))),
          Math.max(0,Math.min(height,Math.round((clientY-rect.top)*height/rect.height)))];
}
function ordered_roi(a,b){return [Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];}
const api={apply_mask_rgba,image_point,ordered_roi};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
else root.PickGoVision=api;
})(typeof globalThis!=='undefined'?globalThis:this);
